from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator

from app.core.metrics import metrics
from app.core.ollama import OllamaClient
from app.db.repository import MetadataRepository
from app.ingestion.chunking import estimate_tokens
from app.models.schemas import ChatRequest, ChatResponse, SearchHit, SearchRequest
from app.retrieval.hybrid import HybridRetrievalService


SYSTEM_PROMPT = """You are Private Research Copilot, an offline research assistant.
Answer only from the supplied context. Cite every factual claim with source labels like [S1].
If the context is insufficient, say what is missing instead of guessing.
Keep answers concise unless the user asks for depth."""


class RAGService:
    def __init__(
        self,
        *,
        repository: MetadataRepository,
        retrieval: HybridRetrievalService,
        ollama: OllamaClient,
        default_model: str,
        recent_messages: int,
        max_context_chars: int,
    ) -> None:
        self.repository = repository
        self.retrieval = retrieval
        self.ollama = ollama
        self.default_model = default_model
        self.recent_messages = recent_messages
        self.max_context_chars = max_context_chars

    async def answer(self, request: ChatRequest) -> ChatResponse:
        start = time.perf_counter()
        model = request.model or self.default_model
        conversation_id = self.repository.ensure_conversation(
            request.conversation_id,
            title=request.message[:80],
        )
        self.repository.add_message(conversation_id, "user", request.message)

        retrieval_request = request.retrieval or SearchRequest(
            query=request.message,
            top_k=6,
        )
        retrieval_request.query = request.message
        search_response = await self.retrieval.search(retrieval_request)
        messages = self._build_messages(conversation_id, request.message, search_response.hits)

        with metrics.timer("ollama.chat"):
            answer = await self.ollama.chat(
                model=model,
                messages=messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
        token_count = estimate_tokens(answer)
        elapsed = time.perf_counter() - start
        self.repository.add_message(
            conversation_id,
            "assistant",
            answer,
            metadata={"sources": [source.model_dump() for source in search_response.hits], "model": model},
        )
        metrics.increment("chat.requests")
        metrics.observe("chat.latency", elapsed)
        return ChatResponse(
            conversation_id=conversation_id,
            model=model,
            answer=answer,
            sources=search_response.hits,
            latency_ms=elapsed * 1000,
            token_count=token_count,
            tokens_per_second=token_count / elapsed if elapsed > 0 else 0.0,
        )

    async def stream_answer(self, request: ChatRequest) -> AsyncIterator[str]:
        start = time.perf_counter()
        model = request.model or self.default_model
        conversation_id = self.repository.ensure_conversation(
            request.conversation_id,
            title=request.message[:80],
        )
        self.repository.add_message(conversation_id, "user", request.message)
        retrieval_request = request.retrieval or SearchRequest(query=request.message, top_k=6)
        retrieval_request.query = request.message
        search_response = await self.retrieval.search(retrieval_request)
        yield _sse("sources", {"conversation_id": conversation_id, "sources": _dump_hits(search_response.hits)})

        messages = self._build_messages(conversation_id, request.message, search_response.hits)
        answer_parts: list[str] = []
        async for event in self.ollama.stream_chat(
            model=model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        ):
            if event["type"] == "token":
                answer_parts.append(event["token"])
                yield _sse("token", {"token": event["token"]})

        answer = "".join(answer_parts)
        elapsed = time.perf_counter() - start
        token_count = estimate_tokens(answer)
        self.repository.add_message(
            conversation_id,
            "assistant",
            answer,
            metadata={"sources": _dump_hits(search_response.hits), "model": model},
        )
        metrics.increment("chat.stream_requests")
        metrics.observe("chat.latency", elapsed)
        yield _sse(
            "done",
            {
                "conversation_id": conversation_id,
                "latency_ms": elapsed * 1000,
                "token_count": token_count,
                "tokens_per_second": token_count / elapsed if elapsed > 0 else 0.0,
            },
        )

    def _build_messages(
        self,
        conversation_id: str,
        user_message: str,
        sources: list[SearchHit],
    ) -> list[dict[str, str]]:
        context = self._format_context(sources)
        messages = [{"role": "system", "content": f"{SYSTEM_PROMPT}\n\nContext:\n{context}"}]
        for message in self.repository.recent_messages(conversation_id, limit=self.recent_messages):
            if message["role"] in {"user", "assistant"} and message["content"] != user_message:
                messages.append({"role": message["role"], "content": message["content"]})
        messages.append({"role": "user", "content": user_message})
        return messages

    def _format_context(self, sources: list[SearchHit]) -> str:
        blocks = []
        used = 0
        for index, source in enumerate(sources, start=1):
            label = source.citation or f"S{index}"
            block = (
                f"[{label}] {source.source_name} chunk={source.ordinal} "
                f"path={source.source_path}\n{source.text}"
            )
            if used + len(block) > self.max_context_chars:
                break
            blocks.append(block)
            used += len(block)
        if not blocks:
            return "No retrieved context was available."
        return "\n\n".join(blocks)


def _dump_hits(hits: list[SearchHit]) -> list[dict]:
    return [hit.model_dump() for hit in hits]


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=True)}\n\n"

