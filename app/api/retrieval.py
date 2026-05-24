from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import retrieval_service
from app.models.schemas import SearchRequest, SearchResponse
from app.retrieval.hybrid import HybridRetrievalService

router = APIRouter(prefix="/api/search", tags=["retrieval"])


@router.post("", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    retrieval: HybridRetrievalService = Depends(retrieval_service),
):
    return await retrieval.search(request)

