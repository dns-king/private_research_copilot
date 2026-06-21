# Evaluation Methodology

The evaluation runner measures both retrieval and generation behavior with local-only signals.

## Metrics

- Retrieval precision: fraction of expected source identifiers found in retrieved sources.
- Answer relevance: lexical overlap between expected answer text and generated answer.
- Citation coverage: fraction of answer sentences containing `[S#]` citations.
- Hallucination rate: `1 - citation_coverage`, used as a conservative proxy for unsupported claims.
- Latency: end-to-end milliseconds per case.
- Token throughput: estimated generated tokens per second.
- Memory usage: exposed by `/metrics` through process RSS and system memory percentage.

## Running Benchmarks

1. Start Qdrant and Ollama.
2. Ingest a representative corpus.
3. Edit `docs/sample_eval_cases.json` with domain questions and expected source names.
4. Run:

```bash
python scripts/benchmark.py --cases docs/sample_eval_cases.json --out data/exports/report.json
```

Reports are also saved in SQLite and visible in the Evaluation dashboard.

## Experiment Matrix

Recommended retrieval experiments:

- `chunk_size`: 500, 900, 1400
- `chunk_overlap`: 50, 160, 300
- `embedding_model`: `nomic-embed-text`, `mxbai-embed-large`
- `hybrid_alpha`: 0.35, 0.62, 0.85
- `top_k`: 4, 6, 10

Keep the corpus and questions fixed for each run and compare aggregate relevance, source precision, latency, and memory.
