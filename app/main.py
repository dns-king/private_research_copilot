from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import chat, evaluation, health, ingestion, models, retrieval
from app.core.config import get_settings
from app.core.logging import RequestLoggingMiddleware, configure_logging
from app.core.ollama import OllamaClient
from app.core.tasks import BackgroundTaskQueue
from app.db.repository import MetadataRepository
from app.evaluation.metrics import EvaluationService
from app.generation.rag import RAGService
from app.ingestion.pipeline import IngestionPipeline
from app.retrieval.hybrid import HybridRetrievalService, RetrievalConfig
from app.retrieval.vector_store import QdrantVectorStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    repository = MetadataRepository(settings.database_path)
    ollama = OllamaClient(settings.ollama_base_url, timeout_s=settings.request_timeout_s)
    vector_store = QdrantVectorStore(
        url=settings.qdrant_url,
        collection_prefix=settings.qdrant_collection_prefix,
        embedding_model=settings.embedding_model,
        timeout_s=settings.request_timeout_s,
    )
    retrieval_service = HybridRetrievalService(
        repository=repository,
        vector_store=vector_store,
        ollama=ollama,
        config=RetrievalConfig(
            embedding_model=settings.embedding_model,
            default_model=settings.default_chat_model,
            default_top_k=settings.default_top_k,
            hybrid_alpha=settings.hybrid_alpha,
            vector_expansion_factor=settings.vector_expansion_factor,
            enable_query_decomposition=settings.enable_query_decomposition,
            enable_contextual_compression=settings.enable_contextual_compression,
        ),
    )
    ingestion_pipeline = IngestionPipeline(
        repository=repository,
        vector_store=vector_store,
        ollama=ollama,
        embedding_model=settings.embedding_model,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    rag_service = RAGService(
        repository=repository,
        retrieval=retrieval_service,
        ollama=ollama,
        default_model=settings.default_chat_model,
        recent_messages=settings.recent_messages,
        max_context_chars=settings.max_context_chars,
    )
    evaluation_service = EvaluationService(repository, rag_service)
    task_queue = BackgroundTaskQueue(default_retries=settings.task_retries)
    await task_queue.start(workers=1)

    app.state.settings = settings
    app.state.repository = repository
    app.state.ollama = ollama
    app.state.vector_store = vector_store
    app.state.retrieval_service = retrieval_service
    app.state.ingestion_pipeline = ingestion_pipeline
    app.state.rag_service = rag_service
    app.state.evaluation_service = evaluation_service
    app.state.task_queue = task_queue
    try:
        yield
    finally:
        await task_queue.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(models.router)
    app.include_router(ingestion.router)
    app.include_router(retrieval.router)
    app.include_router(chat.router)
    app.include_router(evaluation.router)
    app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")

    @app.get("/")
    async def index():
        return FileResponse(settings.static_dir / "index.html")

    return app


app = create_app()

