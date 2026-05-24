from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class DocumentRecord(BaseModel):
    id: str
    name: str
    path: str
    mime_type: str | None = None
    size_bytes: int = 0
    content_hash: str
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class ChunkRecord(BaseModel):
    id: str
    document_id: str
    ordinal: int
    text: str
    token_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestionRequest(BaseModel):
    path: str
    recursive: bool = True
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    strategy: Literal["recursive", "sentence", "token"] = "recursive"
    embedding_model: str | None = None


class IngestionJob(BaseModel):
    id: str
    source_path: str
    status: Literal["queued", "running", "completed", "failed"]
    total_files: int = 0
    processed_files: int = 0
    error: str | None = None
    created_at: str
    updated_at: str


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=6, ge=1, le=50)
    model: str | None = None
    embedding_model: str | None = None
    hybrid_alpha: float = Field(default=0.62, ge=0.0, le=1.0)
    decompose_query: bool = True
    compress_context: bool = True
    rerank: bool = True


class SearchHit(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    score: float
    vector_score: float = 0.0
    bm25_score: float = 0.0
    source_name: str
    source_path: str
    ordinal: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    citation: str | None = None


class SearchResponse(BaseModel):
    query: str
    expanded_queries: list[str]
    hits: list[SearchHit]
    latency_ms: float


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    conversation_id: str | None = None
    model: str | None = None
    retrieval: SearchRequest | None = None
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=64, le=8192)


class ChatResponse(BaseModel):
    conversation_id: str
    model: str
    answer: str
    sources: list[SearchHit]
    latency_ms: float
    token_count: int
    tokens_per_second: float


class EvaluationCase(BaseModel):
    question: str
    expected_answer: str | None = None
    expected_sources: list[str] = Field(default_factory=list)
    model: str | None = None
    top_k: int = Field(default=6, ge=1, le=50)


class EvaluationRunRequest(BaseModel):
    name: str = Field(default_factory=lambda: f"eval-{datetime.utcnow().isoformat()}")
    cases: list[EvaluationCase]


class EvaluationResult(BaseModel):
    question: str
    answer: str
    metrics: dict[str, float]
    sources: list[SearchHit]
    latency_ms: float


class EvaluationReport(BaseModel):
    id: str
    name: str
    created_at: str
    aggregate: dict[str, float]
    results: list[EvaluationResult]
