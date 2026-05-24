from __future__ import annotations

import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MetadataRepository:
    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    path TEXT NOT NULL,
                    mime_type TEXT,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    content_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    token_count INTEGER NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ingestion_jobs (
                    id TEXT PRIMARY KEY,
                    source_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    total_files INTEGER NOT NULL DEFAULT 0,
                    processed_files INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS evaluation_reports (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            try:
                conn.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts "
                    "USING fts5(chunk_id UNINDEXED, document_id UNINDEXED, text)"
                )
            except sqlite3.OperationalError:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS chunks_fts_fallback (
                        chunk_id TEXT PRIMARY KEY,
                        document_id TEXT NOT NULL,
                        text TEXT NOT NULL
                    )
                    """
                )

    def upsert_document(self, record: dict[str, Any]) -> None:
        now = utc_now()
        metadata_json = json.dumps(record.get("metadata", {}), ensure_ascii=True)
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT created_at FROM documents WHERE id = ?", (record["id"],)
            ).fetchone()
            conn.execute(
                """
                INSERT INTO documents (
                    id, name, path, mime_type, size_bytes, content_hash, status,
                    metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    path=excluded.path,
                    mime_type=excluded.mime_type,
                    size_bytes=excluded.size_bytes,
                    content_hash=excluded.content_hash,
                    status=excluded.status,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                (
                    record["id"],
                    record["name"],
                    record["path"],
                    record.get("mime_type"),
                    int(record.get("size_bytes", 0)),
                    record["content_hash"],
                    record.get("status", "indexed"),
                    metadata_json,
                    existing["created_at"] if existing else now,
                    now,
                ),
            )

    def delete_chunks_for_document(self, document_id: str) -> None:
        with self.connect() as conn:
            rows = conn.execute("SELECT id FROM chunks WHERE document_id = ?", (document_id,)).fetchall()
            chunk_ids = [row["id"] for row in rows]
            conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
            for chunk_id in chunk_ids:
                self._delete_fts(conn, chunk_id)

    def upsert_chunk(self, record: dict[str, Any]) -> None:
        metadata_json = json.dumps(record.get("metadata", {}), ensure_ascii=True)
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO chunks (
                    id, document_id, ordinal, text, token_count, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    text=excluded.text,
                    token_count=excluded.token_count,
                    metadata_json=excluded.metadata_json
                """,
                (
                    record["id"],
                    record["document_id"],
                    int(record["ordinal"]),
                    record["text"],
                    int(record["token_count"]),
                    metadata_json,
                    now,
                ),
            )
            self._delete_fts(conn, record["id"])
            try:
                conn.execute(
                    "INSERT INTO chunks_fts(chunk_id, document_id, text) VALUES (?, ?, ?)",
                    (record["id"], record["document_id"], record["text"]),
                )
            except sqlite3.OperationalError:
                conn.execute(
                    """
                    INSERT INTO chunks_fts_fallback(chunk_id, document_id, text)
                    VALUES (?, ?, ?)
                    ON CONFLICT(chunk_id) DO UPDATE SET
                        document_id=excluded.document_id,
                        text=excluded.text
                    """,
                    (record["id"], record["document_id"], record["text"]),
                )

    def list_documents(self, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM documents ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._decode_document(row) for row in rows]

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        return self._decode_document(row) if row else None

    def get_chunks(self, chunk_ids: Iterable[str]) -> list[dict[str, Any]]:
        ids = list(dict.fromkeys(chunk_ids))
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT c.*, d.name AS source_name, d.path AS source_path
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE c.id IN ({placeholders})
                """,
                ids,
            ).fetchall()
        records = [self._decode_chunk(row) for row in rows]
        return sorted(records, key=lambda item: ids.index(item["id"]))

    def all_chunks(self, limit: int = 100_000) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT c.*, d.name AS source_name, d.path AS source_path
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._decode_chunk(row) for row in rows]

    def search_bm25(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        fts_query = _to_fts_query(query)
        if not fts_query:
            return []
        with self.connect() as conn:
            try:
                rows = conn.execute(
                    """
                    SELECT chunk_id, document_id, bm25(chunks_fts) AS raw_score
                    FROM chunks_fts
                    WHERE chunks_fts MATCH ?
                    ORDER BY raw_score
                    LIMIT ?
                    """,
                    (fts_query, limit),
                ).fetchall()
                return [
                    {
                        "chunk_id": row["chunk_id"],
                        "document_id": row["document_id"],
                        "score": 1.0 / (rank + 1),
                    }
                    for rank, row in enumerate(rows)
                ]
            except sqlite3.OperationalError:
                rows = conn.execute("SELECT * FROM chunks_fts_fallback").fetchall()
        return _fallback_bm25(query, rows, limit)

    def create_job(self, source_path: str, status: str = "queued") -> str:
        job_id = str(uuid.uuid4())
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO ingestion_jobs (
                    id, source_path, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, source_path, status, now, now),
            )
        return job_id

    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        total_files: int | None = None,
        processed_files: int | None = None,
        error: str | None = None,
    ) -> None:
        fields = []
        values: list[Any] = []
        for key, value in {
            "status": status,
            "total_files": total_files,
            "processed_files": processed_files,
            "error": error,
        }.items():
            if value is not None:
                fields.append(f"{key} = ?")
                values.append(value)
        fields.append("updated_at = ?")
        values.append(utc_now())
        values.append(job_id)
        with self.connect() as conn:
            conn.execute(f"UPDATE ingestion_jobs SET {', '.join(fields)} WHERE id = ?", values)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM ingestion_jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM ingestion_jobs ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def ensure_conversation(self, conversation_id: str | None, title: str | None = None) -> str:
        now = utc_now()
        cid = conversation_id or str(uuid.uuid4())
        with self.connect() as conn:
            existing = conn.execute("SELECT id FROM conversations WHERE id = ?", (cid,)).fetchone()
            if existing:
                conn.execute(
                    "UPDATE conversations SET updated_at = ?, title = COALESCE(title, ?) WHERE id = ?",
                    (now, title, cid),
                )
            else:
                conn.execute(
                    "INSERT INTO conversations(id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (cid, title, now, now),
                )
        return cid

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        message_id = str(uuid.uuid4())
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO messages(id, conversation_id, role, content, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    conversation_id,
                    role,
                    content,
                    json.dumps(metadata or {}, ensure_ascii=True),
                    now,
                ),
            )
            conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id))
        return message_id

    def recent_messages(self, conversation_id: str, limit: int = 8) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (conversation_id, limit),
            ).fetchall()
        return [
            {
                "role": row["role"],
                "content": row["content"],
                "metadata": _loads(row["metadata_json"]),
                "created_at": row["created_at"],
            }
            for row in reversed(rows)
        ]

    def save_evaluation_report(self, report: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO evaluation_reports(id, name, report_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    report["id"],
                    report["name"],
                    json.dumps(report, ensure_ascii=True),
                    report["created_at"],
                ),
            )

    def list_evaluation_reports(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT report_json FROM evaluation_reports ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [json.loads(row["report_json"]) for row in rows]

    def _delete_fts(self, conn: sqlite3.Connection, chunk_id: str) -> None:
        try:
            conn.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk_id,))
        except sqlite3.OperationalError:
            conn.execute("DELETE FROM chunks_fts_fallback WHERE chunk_id = ?", (chunk_id,))

    def _decode_document(self, row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["metadata"] = _loads(record.pop("metadata_json"))
        return record

    def _decode_chunk(self, row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["metadata"] = _loads(record.pop("metadata_json"))
        return record


def _loads(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _to_fts_query(query: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9_]{2,}", query.lower())
    tokens = list(dict.fromkeys(tokens))[:12]
    return " OR ".join(tokens)


def _fallback_bm25(query: str, rows: list[sqlite3.Row], limit: int) -> list[dict[str, Any]]:
    query_terms = set(re.findall(r"[A-Za-z0-9_]{2,}", query.lower()))
    scored = []
    for row in rows:
        text_terms = re.findall(r"[A-Za-z0-9_]{2,}", row["text"].lower())
        if not text_terms:
            continue
        score = sum(1 for term in text_terms if term in query_terms) / max(len(text_terms), 1)
        if score > 0:
            scored.append(
                {
                    "chunk_id": row["chunk_id"],
                    "document_id": row["document_id"],
                    "score": score,
                }
            )
    return sorted(scored, key=lambda item: item["score"], reverse=True)[:limit]

