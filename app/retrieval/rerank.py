from __future__ import annotations

import re

from app.models.schemas import SearchHit


def rerank_hits(query: str, hits: list[SearchHit]) -> list[SearchHit]:
    query_terms = _terms(query)
    if not query_terms:
        return hits
    reranked = []
    for hit in hits:
        text_terms = _terms(hit.text)
        overlap = len(query_terms & text_terms) / max(len(query_terms), 1)
        hit.score = (hit.score * 0.84) + (overlap * 0.16)
        reranked.append(hit)
    return sorted(reranked, key=lambda item: item.score, reverse=True)


def compress_hit(query: str, hit: SearchHit, max_chars: int = 1400) -> SearchHit:
    if len(hit.text) <= max_chars:
        return hit
    query_terms = _terms(query)
    sentences = re.split(r"(?<=[.!?])\s+", hit.text)
    selected = []
    for sentence in sentences:
        if _terms(sentence) & query_terms:
            selected.append(sentence.strip())
        if sum(len(item) for item in selected) >= max_chars:
            break
    if not selected:
        selected = [hit.text[:max_chars]]
    compressed = " ".join(selected).strip()
    hit.text = compressed[:max_chars]
    hit.metadata["compressed"] = True
    return hit


def _terms(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9_]{3,}", text.lower()))

