from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal


ChunkStrategy = Literal["recursive", "sentence", "token"]


@dataclass
class TextChunk:
    ordinal: int
    text: str
    token_count: int
    metadata: dict[str, Any]


class Chunker:
    def __init__(self, chunk_size: int = 900, chunk_overlap: int = 160, strategy: ChunkStrategy = "recursive"):
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.strategy = strategy

    def split(self, text: str, metadata: dict[str, Any] | None = None) -> list[TextChunk]:
        metadata = metadata or {}
        if not text.strip():
            return []
        if self.strategy == "recursive":
            pieces = self._recursive_split(text)
        elif self.strategy == "sentence":
            pieces = self._sentence_split(text)
        else:
            pieces = self._token_split(text)
        chunks = []
        for ordinal, piece in enumerate(pieces):
            chunk_metadata = dict(metadata)
            chunk_metadata["chunk_strategy"] = self.strategy
            chunks.append(
                TextChunk(
                    ordinal=ordinal,
                    text=piece.strip(),
                    token_count=estimate_tokens(piece),
                    metadata=chunk_metadata,
                )
            )
        return chunks

    def _recursive_split(self, text: str) -> list[str]:
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter

            splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                separators=["\n\n", "\n", ". ", " ", ""],
            )
            return [chunk for chunk in splitter.split_text(text) if chunk.strip()]
        except Exception:
            return self._sentence_split(text)

    def _sentence_split(self, text: str) -> list[str]:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks: list[str] = []
        current = ""
        for sentence in sentences:
            candidate = f"{current} {sentence}".strip()
            if len(candidate) <= self.chunk_size or not current:
                current = candidate
                continue
            chunks.append(current)
            overlap = current[-self.chunk_overlap :] if self.chunk_overlap else ""
            current = f"{overlap} {sentence}".strip()
        if current:
            chunks.append(current)
        return chunks

    def _token_split(self, text: str) -> list[str]:
        words = text.split()
        if not words:
            return []
        approx_words = max(1, int(self.chunk_size / 5))
        overlap_words = min(max(0, int(self.chunk_overlap / 5)), approx_words - 1)
        chunks = []
        start = 0
        while start < len(words):
            end = min(len(words), start + approx_words)
            chunks.append(" ".join(words[start:end]))
            if end == len(words):
                break
            start = max(0, end - overlap_words)
        return chunks


def estimate_tokens(text: str) -> int:
    return max(1, int(len(re.findall(r"\S+", text)) * 1.3))

