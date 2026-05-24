from __future__ import annotations

import json
import re

from app.core.ollama import OllamaClient


async def decompose_query(
    query: str,
    *,
    ollama: OllamaClient,
    model: str,
    enabled: bool = True,
) -> list[str]:
    if not enabled or len(query.split()) < 8:
        return [query]
    prompt = (
        "Break the research question into at most three concise search queries. "
        "Return only a JSON array of strings.\n\nQuestion: "
        f"{query}"
    )
    try:
        raw = await ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=160,
        )
        parsed = json.loads(_extract_json_array(raw))
        queries = [item.strip() for item in parsed if isinstance(item, str) and item.strip()]
        return list(dict.fromkeys([query, *queries]))[:4]
    except Exception:
        return _heuristic_decompose(query)


def _extract_json_array(raw: str) -> str:
    match = re.search(r"\[[\s\S]*\]", raw)
    return match.group(0) if match else raw


def _heuristic_decompose(query: str) -> list[str]:
    parts = re.split(r"\b(?:and|versus|vs\.?|compare|contrast)\b|[;:]", query, flags=re.I)
    cleaned = [part.strip(" ?.") for part in parts if len(part.strip()) > 8]
    return list(dict.fromkeys([query, *cleaned]))[:4]

