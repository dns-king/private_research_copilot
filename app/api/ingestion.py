from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.deps import ingestion_pipeline, repository, settings, task_queue
from app.db.repository import MetadataRepository
from app.ingestion.loaders import SUPPORTED_EXTENSIONS
from app.ingestion.pipeline import IngestionPipeline
from app.models.schemas import IngestionRequest

router = APIRouter(prefix="/api/ingest", tags=["ingestion"])


@router.post("/path")
async def ingest_path(
    request: IngestionRequest,
    repo: MetadataRepository = Depends(repository),
    pipeline: IngestionPipeline = Depends(ingestion_pipeline),
    queue=Depends(task_queue),
):
    source = Path(request.path).expanduser()
    if not source.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {request.path}")
    job_id = repo.create_job(str(source), status="queued")
    await queue.enqueue(
        f"ingest:{job_id}",
        pipeline.ingest_path,
        source,
        job_id=job_id,
        recursive=request.recursive,
        chunk_size=request.chunk_size,
        chunk_overlap=request.chunk_overlap,
        strategy=request.strategy,
        embedding_model=request.embedding_model,
    )
    return {"job_id": job_id, "status": "queued"}


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    repo: MetadataRepository = Depends(repository),
    pipeline: IngestionPipeline = Depends(ingestion_pipeline),
    queue=Depends(task_queue),
    cfg=Depends(settings),
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")
    destination = cfg.upload_dir / Path(file.filename or "upload").name
    with destination.open("wb") as handle:
        shutil.copyfileobj(file.file, handle)
    job_id = repo.create_job(str(destination), status="queued")
    await queue.enqueue(f"ingest-upload:{job_id}", pipeline.ingest_path, destination, job_id=job_id)
    return {"job_id": job_id, "status": "queued", "path": str(destination)}


@router.get("/jobs")
async def list_jobs(repo: MetadataRepository = Depends(repository)):
    return {"jobs": repo.list_jobs()}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, repo: MetadataRepository = Depends(repository)):
    job = repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/documents")
async def list_documents(repo: MetadataRepository = Depends(repository)):
    return {"documents": repo.list_documents(limit=500)}

