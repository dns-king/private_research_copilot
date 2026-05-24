from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import evaluation_service, repository
from app.db.repository import MetadataRepository
from app.evaluation.metrics import EvaluationService
from app.models.schemas import EvaluationReport, EvaluationRunRequest

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])


@router.post("/run", response_model=EvaluationReport)
async def run_evaluation(
    request: EvaluationRunRequest,
    evaluator: EvaluationService = Depends(evaluation_service),
):
    return await evaluator.run(request)


@router.get("/reports")
async def list_reports(repo: MetadataRepository = Depends(repository)):
    return {"reports": repo.list_evaluation_reports()}

