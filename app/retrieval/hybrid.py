from __future__ import annotations

import time
from dataclasses import dataclass

from app.core.metrics import metrics
from app.core.ollama import OllamaClient
from app.db.repository import MetadataRepository
from app.models.schemas import SearchHit, SearchRequest, SearchResponse
from app.retrieval.query import decompose_query
from app.retrieval.rerank import compress_hit, rerank_hits
from app.retrieval.vector_store import QdrantVectorStore


@dataclass
class RetrievalConfig:
    embedding_model: str
    default_model: str
    default_top_k: int
    hybrid_alpha: float
    vector_expansion_factor: int
    enable_query_decomposition: bool
    enable_contextual_compression: bool


class HybridRetrievalService:
    def __init__(
        self,
        *,
        repository: MetadataRepository,
        vector_store: QdrantVectorStore,
        ollama: OllamaClient,
        config: RetrievalConfig,
    ) -> None:
        self.repository = repository
        self.vector_store = vector_store
        self.ollama = ollama
        self.config = config

    async def search(self, request: SearchRequest) -> SearchResponse:
        start = time.perf_counter()
        model = request.model or self.config.default_model
        embedding_model = request.embedding_model or self.config.embedding_model
        top_k = request.top_k or self.config.default_top_k
        expanded_queries = await decompose_query(
            request.query,
            ollama=self.ollama,
            model=model,
            enabled=request.decompose_query and self.config.enable_query_decomposition,
        )
        combined: dict[str, SearchHit] = {}
        for query in expanded_queries:
            await self._merge_query_results(query, combined, top_k, embedding_model, request.hybrid_alpha)
        hits = sorted(combined.values(), key=lambda item: item.score, reverse=True)
        if request.rerank:
            hits = rerank_hits(request.query, hits)
        hits = hits[:top_k]
        if request.compress_context and self.config.enable_contextual_compression:
            hits = [compress_hit(request.query, hit) for hit in hits]
        for index, hit in enumerate(hits, start=1):
            hit.citation = f"S{index}"
        latency_ms = (time.perf_counter() - start) * 1000
        metrics.observe("retrieval.latency", latency_ms / 1000)
        metrics.increment("retrieval.requests")
        return SearchResponse(
            query=request.query,
            expanded_queries=expanded_queries,
            hits=hits,
            latency_ms=latency_ms,
        )

    async def _merge_query_results(
        self,
        query: str,
        combined: dict[str, SearchHit],
        top_k: int,
        embedding_model: str,
        hybrid_alpha: float,
    ) -> None:
        expansion_limit = max(top_k * self.config.vector_expansion_factor, top_k)
        vector_score_by_id: dict[str, float] = {}
        try:
            vectors = await self.ollama.embed([query], model=embedding_model)
            vector_hits = await self.vector_store.search(
                vectors[0],
                limit=expansion_limit,
                embedding_model=embedding_model,
            )
            for rank, hit in enumerate(vector_hits):
                rank_score = 1.0 / (rank + 1)
                vector_score_by_id[hit.chunk_id] = max(hit.score, rank_score)
                combined[hit.chunk_id] = _hit_from_payload(
                    hit.payload,
                    score=hybrid_alpha * vector_score_by_id[hit.chunk_id],
                    vector_score=vector_score_by_id[hit.chunk_id],
                    bm25_score=0.0,
                )
        except Exception:
            metrics.increment("retrieval.vector_failures")

        bm25_hits = self.repository.search_bm25(query, limit=expansion_limit)
        bm25_chunks = {chunk["id"]: chunk for chunk in self.repository.get_chunks(h["chunk_id"] for h in bm25_hits)}
        for bm25_hit in bm25_hits:
            chunk_id = bm25_hit["chunk_id"]
            chunk = bm25_chunks.get(chunk_id)
            if not chunk:
                continue
            bm25_score = float(bm25_hit["score"])
            vector_score = vector_score_by_id.get(chunk_id, 0.0)
            score = (hybrid_alpha * vector_score) + ((1 - hybrid_alpha) * bm25_score)
            existing = combined.get(chunk_id)
            if existing:
                existing.score = max(existing.score, score)
                existing.bm25_score = max(existing.bm25_score, bm25_score)
                existing.vector_score = max(existing.vector_score, vector_score)
            else:
                combined[chunk_id] = SearchHit(
                    chunk_id=chunk_id,
                    document_id=chunk["document_id"],
                    text=chunk["text"],
                    score=score,
                    vector_score=vector_score,
                    bm25_score=bm25_score,
                    source_name=chunk.get("source_name", ""),
                    source_path=chunk.get("source_path", ""),
                    ordinal=int(chunk["ordinal"]),
                    metadata=chunk.get("metadata", {}),
                )


def _hit_from_payload(
    payload: dict,
    *,
    score: float,
    vector_score: float,
    bm25_score: float,
) -> SearchHit:
    return SearchHit(
        chunk_id=payload.get("chunk_id", ""),
        document_id=payload.get("document_id", ""),
        text=payload.get("text", ""),
        score=score,
        vector_score=vector_score,
        bm25_score=bm25_score,
        source_name=payload.get("source_name", ""),
        source_path=payload.get("source_path", ""),
        ordinal=int(payload.get("ordinal", 0)),
        metadata=payload.get("metadata", {}),
    )
