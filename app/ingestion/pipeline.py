from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from app.core.metrics import metrics
from app.core.ollama import OllamaClient
from app.db.repository import MetadataRepository
from app.ingestion.chunking import ChunkStrategy, Chunker
from app.ingestion.loaders import LoadedDocument, discover_files, load_document
from app.retrieval.vector_store import QdrantVectorStore


class IngestionPipeline:
    def __init__(
        self,
        *,
        repository: MetadataRepository,
        vector_store: QdrantVectorStore,
        ollama: OllamaClient,
        embedding_model: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> None:
        self.repository = repository
        self.vector_store = vector_store
        self.ollama = ollama
        self.embedding_model = embedding_model
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.logger = logging.getLogger("app.ingestion")

    async def ingest_path(
        self,
        path: str | Path,
        *,
        job_id: str | None = None,
        recursive: bool = True,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        strategy: ChunkStrategy = "recursive",
        embedding_model: str | None = None,
    ) -> dict[str, Any]:
        files = discover_files(path, recursive=recursive)
        if job_id:
            self.repository.update_job(job_id, status="running", total_files=len(files), processed_files=0)
        processed = 0
        try:
            for file_path in files:
                await self.ingest_file(
                    file_path,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                    strategy=strategy,
                    embedding_model=embedding_model,
                )
                processed += 1
                if job_id:
                    self.repository.update_job(job_id, processed_files=processed)
            if job_id:
                self.repository.update_job(job_id, status="completed", processed_files=processed)
            return {"files": len(files), "processed": processed}
        except Exception as exc:
            if job_id:
                self.repository.update_job(job_id, status="failed", error=str(exc))
            raise

    async def ingest_file(
        self,
        path: str | Path,
        *,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        strategy: ChunkStrategy = "recursive",
        embedding_model: str | None = None,
    ) -> dict[str, Any]:
        with metrics.timer("ingestion.file"):
            active_embedding_model = embedding_model or self.embedding_model
            loaded = load_document(path)
            document_id = _document_id(loaded)
            chunker = Chunker(
                chunk_size=chunk_size or self.chunk_size,
                chunk_overlap=chunk_overlap if chunk_overlap is not None else self.chunk_overlap,
                strategy=strategy,
            )
            chunks = chunker.split(
                loaded.text,
                metadata={
                    **loaded.metadata,
                    "document_id": document_id,
                    "source_path": str(loaded.path),
                    "source_name": loaded.path.name,
                    "content_hash": loaded.content_hash,
                    "embedding_model": active_embedding_model,
                },
            )
            self.repository.upsert_document(
                {
                    "id": document_id,
                    "name": loaded.path.name,
                    "path": str(loaded.path),
                    "mime_type": loaded.mime_type,
                    "size_bytes": loaded.size_bytes,
                    "content_hash": loaded.content_hash,
                    "status": "indexing",
                    "metadata": loaded.metadata,
                }
            )
            self.repository.delete_chunks_for_document(document_id)
            await self.vector_store.delete_document(
                document_id,
                embedding_model=active_embedding_model,
            )

            if not chunks:
                self.repository.upsert_document(
                    {
                        "id": document_id,
                        "name": loaded.path.name,
                        "path": str(loaded.path),
                        "mime_type": loaded.mime_type,
                        "size_bytes": loaded.size_bytes,
                        "content_hash": loaded.content_hash,
                        "status": "empty",
                        "metadata": loaded.metadata,
                    }
                )
                return {"document_id": document_id, "chunks": 0}

            texts = [chunk.text for chunk in chunks]
            vectors = await self._embed_batches(texts, active_embedding_model)
            points = []
            for chunk, vector in zip(chunks, vectors, strict=True):
                chunk_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{document_id}:{chunk.ordinal}"))
                payload = {
                    "chunk_id": chunk_id,
                    "document_id": document_id,
                    "text": chunk.text,
                    "source_name": loaded.path.name,
                    "source_path": str(loaded.path),
                    "ordinal": chunk.ordinal,
                    "metadata": chunk.metadata,
                }
                points.append({"point_id": chunk_id, "payload": payload})
                self.repository.upsert_chunk(
                    {
                        "id": chunk_id,
                        "document_id": document_id,
                        "ordinal": chunk.ordinal,
                        "text": chunk.text,
                        "token_count": chunk.token_count,
                        "metadata": chunk.metadata,
                    }
                )
            await self.vector_store.upsert(points, vectors, embedding_model=active_embedding_model)
            self.repository.upsert_document(
                {
                    "id": document_id,
                    "name": loaded.path.name,
                    "path": str(loaded.path),
                    "mime_type": loaded.mime_type,
                    "size_bytes": loaded.size_bytes,
                    "content_hash": loaded.content_hash,
                    "status": "indexed",
                    "metadata": {
                        **loaded.metadata,
                        "chunk_count": len(chunks),
                        "embedding_model": active_embedding_model,
                    },
                }
            )
            metrics.increment("documents_indexed")
            metrics.increment("chunks_indexed", len(chunks))
            return {"document_id": document_id, "chunks": len(chunks)}

    async def _embed_batches(
        self,
        texts: list[str],
        embedding_model: str,
        batch_size: int = 16,
    ) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            with metrics.timer("ollama.embed"):
                vectors.extend(await self.ollama.embed(batch, model=embedding_model))
        return vectors


def _document_id(document: LoadedDocument) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, str(document.path)))
