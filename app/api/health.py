from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from app.api.deps import ollama_client, repository, settings
from app.core.metrics import metrics
from app.core.ollama import OllamaClient
from app.db.repository import MetadataRepository

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(
    repo: MetadataRepository = Depends(repository),
    ollama: OllamaClient = Depends(ollama_client),
    cfg=Depends(settings),
):
    documents = len(repo.list_documents(limit=10_000))
    ollama_ok = True
    try:
        models = await ollama.list_models()
    except Exception:
        ollama_ok = False
        models = []
    return {
        "status": "ok",
        "environment": cfg.env,
        "documents": documents,
        "ollama": {"ok": ollama_ok, "models": models},
        "qdrant_collection": cfg.qdrant_collection_prefix,
    }


@router.get("/metrics")
async def metrics_snapshot():
    return metrics.snapshot()


@router.get("/metrics/prometheus", response_class=PlainTextResponse)
async def prometheus_metrics():
    return metrics.prometheus()

