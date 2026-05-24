from app.db.repository import MetadataRepository


def test_repository_bm25_roundtrip(tmp_path):
    repo = MetadataRepository(tmp_path / "test.db")
    repo.upsert_document(
        {
            "id": "doc-1",
            "name": "paper.md",
            "path": "/tmp/paper.md",
            "mime_type": "text/markdown",
            "size_bytes": 100,
            "content_hash": "abc",
            "status": "indexed",
            "metadata": {},
        }
    )
    repo.upsert_chunk(
        {
            "id": "chunk-1",
            "document_id": "doc-1",
            "ordinal": 0,
            "text": "retrieval augmented generation with local vector search",
            "token_count": 8,
            "metadata": {},
        }
    )
    hits = repo.search_bm25("local vector retrieval", limit=5)
    assert hits
    assert hits[0]["chunk_id"] == "chunk-1"

