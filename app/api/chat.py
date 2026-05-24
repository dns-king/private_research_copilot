from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import rag_service
from app.generation.rag import RAGService
from app.models.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest, rag: RAGService = Depends(rag_service)):
    return await rag.answer(request)


@router.post("/stream")
async def stream_chat(request: ChatRequest, rag: RAGService = Depends(rag_service)):
    return StreamingResponse(rag.stream_answer(request), media_type="text/event-stream")

