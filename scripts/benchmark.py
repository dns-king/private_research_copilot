from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

import httpx


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run local RAG benchmark cases, playa.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--cases", default="docs/sample_eval_cases.json")
    parser.add_argument("--out", default="data/exports/benchmark_report.json")
    args = parser.parse_args()

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    payload = {"name": f"benchmark-{int(time.time())}", "cases": cases}
    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.post(f"{args.base_url}/api/evaluation/run", json=payload)
        response.raise_for_status()
        report = response.json()
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {output}")
    print(json.dumps(report["aggregate"], indent=2))


if __name__ == "__main__":
    asyncio.run(main())

