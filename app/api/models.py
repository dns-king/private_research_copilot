from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import ollama_client, settings
from app.core.ollama import OllamaClient

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("")
async def list_models(ollama: OllamaClient = Depends(ollama_client), cfg=Depends(settings)):
    try:
        installed = await ollama.list_models()
    except Exception:
        installed = []
    return {
        "configured": cfg.configured_chat_models,
        "installed": installed,
        "default_chat_model": cfg.default_chat_model,
        "default_embedding_model": cfg.embedding_model,
    }

