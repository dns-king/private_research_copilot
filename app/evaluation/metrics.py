from __future__ import annotations

import re
import time
import uuid
from collections import defaultdict

from app.db.repository import MetadataRepository, utc_now
from app.generation.rag import RAGService
from app.models.schemas import (
    ChatRequest,
    EvaluationReport,
    EvaluationResult,
    EvaluationRunRequest,
    SearchRequest,
)


class EvaluationService:
    def __init__(self, repository: MetadataRepository, rag: RAGService) -> None:
        self.repository = repository
        self.rag = rag

    async def run(self, request: EvaluationRunRequest) -> EvaluationReport:
        results: list[EvaluationResult] = []
        for case in request.cases:
            start = time.perf_counter()
            response = await self.rag.answer(
                ChatRequest(
                    message=case.question,
                    model=case.model,
                    retrieval=SearchRequest(query=case.question, top_k=case.top_k),
                )
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            metrics = {
                "retrieval_precision": retrieval_precision(case.expected_sources, response.sources),
                "answer_relevance": answer_relevance(case.expected_answer or case.question, response.answer),
                "citation_coverage": citation_coverage(response.answer),
                "hallucination_rate": 1.0 - citation_coverage(response.answer),
                "latency_ms": elapsed_ms,
                "tokens_per_second": response.tokens_per_second,
            }
            results.append(
                EvaluationResult(
                    question=case.question,
                    answer=response.answer,
                    metrics=metrics,
                    sources=response.sources,
                    latency_ms=elapsed_ms,
                )
            )
        aggregate = aggregate_metrics([result.metrics for result in results])
        report = EvaluationReport(
            id=str(uuid.uuid4()),
            name=request.name,
            created_at=utc_now(),
            aggregate=aggregate,
            results=results,
        )
        self.repository.save_evaluation_report(report.model_dump())
        return report


def retrieval_precision(expected_sources: list[str], sources) -> float:
    if not expected_sources:
        return 0.0
    expected = {item.lower() for item in expected_sources}
    observed = {
        value.lower()
        for source in sources
        for value in (source.source_name, source.source_path, source.document_id)
    }
    matched = sum(1 for expected_item in expected if any(expected_item in item for item in observed))
    return matched / len(expected)


def answer_relevance(reference: str, answer: str) -> float:
    reference_terms = _terms(reference)
    answer_terms = _terms(answer)
    if not reference_terms:
        return 0.0
    return len(reference_terms & answer_terms) / len(reference_terms)


def citation_coverage(answer: str) -> float:
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", answer) if sentence.strip()]
    if not sentences:
        return 0.0
    cited = sum(1 for sentence in sentences if re.search(r"\[S\d+\]", sentence))
    return cited / len(sentences)


def aggregate_metrics(metrics: list[dict[str, float]]) -> dict[str, float]:
    buckets: dict[str, list[float]] = defaultdict(list)
    for item in metrics:
        for key, value in item.items():
            buckets[key].append(value)
    return {key: sum(values) / len(values) for key, values in buckets.items() if values}


def _terms(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9_]{3,}", text.lower()))

