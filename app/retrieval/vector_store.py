from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class VectorHit:
    chunk_id: str
    document_id: str
    score: float
    payload: dict[str, Any]


class QdrantVectorStore:
    def __init__(self, url: str, collection_prefix: str, embedding_model: str, timeout_s: float = 60.0) -> None:
        self.url = url
        self.collection_prefix = collection_prefix
        self.default_embedding_model = embedding_model
        self.collection_name = self.collection_name_for(embedding_model)
        self.timeout_s = timeout_s
        self._client = None
        self._dimensions: dict[str, int] = {}

    @property
    def client(self):
        if self._client is None:
            try:
                from qdrant_client import QdrantClient
            except ImportError as exc:
                raise RuntimeError("Install qdrant-client to use vector retrieval") from exc
            if self.url == ":memory:":
                self._client = QdrantClient(":memory:")
            else:
                self._client = QdrantClient(url=self.url, timeout=self.timeout_s)
        return self._client

    def collection_name_for(self, embedding_model: str | None = None) -> str:
        model = embedding_model or self.default_embedding_model
        return f"{self.collection_prefix}_{_safe_name(model)}"

    async def ensure_collection(self, dimension: int, embedding_model: str | None = None) -> None:
        collection_name = self.collection_name_for(embedding_model)
        if self._dimensions.get(collection_name) == dimension:
            return
        await asyncio.to_thread(self._ensure_collection_sync, collection_name, dimension)
        self._dimensions[collection_name] = dimension

    def _ensure_collection_sync(self, collection_name: str, dimension: int) -> None:
        from qdrant_client.models import Distance, VectorParams

        try:
            exists = self.client.collection_exists(collection_name)
        except AttributeError:
            exists = any(
                collection.name == collection_name
                for collection in self.client.get_collections().collections
            )
        if not exists:
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
            )

    async def upsert(
        self,
        points: list[dict[str, Any]],
        vectors: list[list[float]],
        embedding_model: str | None = None,
    ) -> None:
        if not points:
            return
        collection_name = self.collection_name_for(embedding_model)
        await self.ensure_collection(len(vectors[0]), embedding_model=embedding_model)
        await asyncio.to_thread(self._upsert_sync, collection_name, points, vectors)

    def _upsert_sync(self, collection_name: str, points: list[dict[str, Any]], vectors: list[list[float]]) -> None:
        from qdrant_client.models import PointStruct

        structs = [
            PointStruct(id=point["point_id"], vector=vector, payload=point["payload"])
            for point, vector in zip(points, vectors, strict=True)
        ]
        self.client.upsert(collection_name=collection_name, points=structs, wait=True)

    async def delete_document(self, document_id: str, embedding_model: str | None = None) -> None:
        collection_name = self.collection_name_for(embedding_model)
        await asyncio.to_thread(self._delete_document_sync, collection_name, document_id)

    def _delete_document_sync(self, collection_name: str, document_id: str) -> None:
        from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

        try:
            exists = self.client.collection_exists(collection_name)
        except AttributeError:
            exists = any(
                collection.name == collection_name
                for collection in self.client.get_collections().collections
            )
        if not exists:
            return
        self.client.delete(
            collection_name=collection_name,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=document_id),
                        )
                    ]
                )
            ),
            wait=True,
        )

    async def search(
        self,
        query_vector: list[float],
        limit: int = 20,
        embedding_model: str | None = None,
    ) -> list[VectorHit]:
        collection_name = self.collection_name_for(embedding_model)
        await self.ensure_collection(len(query_vector), embedding_model=embedding_model)
        return await asyncio.to_thread(self._search_sync, collection_name, query_vector, limit)

    def _search_sync(self, collection_name: str, query_vector: list[float], limit: int) -> list[VectorHit]:
        try:
            result = self.client.query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=limit,
                with_payload=True,
            ).points
        except AttributeError:
            result = self.client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit,
                with_payload=True,
            )
        hits = []
        for item in result:
            payload = item.payload or {}
            hits.append(
                VectorHit(
                    chunk_id=payload.get("chunk_id", str(item.id)),
                    document_id=payload.get("document_id", ""),
                    score=float(item.score),
                    payload=payload,
                )
            )
        return hits


def _safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_").lower()
