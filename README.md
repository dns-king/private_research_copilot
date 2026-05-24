# Private Research Copilot

Private Research Copilot is a fully local Retrieval-Augmented Generation platform for private document research. It uses Ollama for local models, Qdrant for vector search, SQLite for metadata and BM25, and FastAPI for the API and dashboard.

## What It Includes

- Ollama model switching across Llama 3, Mistral, Gemma, DeepSeek, and Phi.
- PDF, DOCX, TXT, Markdown, and HTML ingestion.
- Recursive, sentence, and token chunking with overlap experiments.
- Qdrant semantic indexing with per-embedding-model collections.
- SQLite FTS5 BM25 hybrid search.
- Query decomposition, reranking, and contextual compression.
- Streaming grounded answers with `[S#]` citations.
- Conversation memory stored locally.
- Evaluation reports for retrieval precision, relevance, hallucination proxy, latency, throughput, and memory.
- Chat, ingestion, evaluation, and performance dashboards.
- Docker Compose deployment with Qdrant and Ollama.

## Quick Start

```powershell
copy .env.example .env
.\scripts\setup.ps1
docker compose up -d qdrant
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`.

Pull the local Ollama models you want to use:

```powershell
ollama pull llama3
ollama pull mistral
ollama pull gemma
ollama pull deepseek-r1
ollama pull phi3
ollama pull nomic-embed-text
```

## Docker

```powershell
copy .env.example .env
docker compose up --build
```

The app runs at `http://127.0.0.1:8000`, Qdrant at `http://127.0.0.1:6333`, and Ollama at `http://127.0.0.1:11434`.

## API

- `POST /api/ingest/path`: ingest a local file or directory.
- `POST /api/ingest/upload`: upload and ingest one supported document.
- `POST /api/search`: hybrid semantic and BM25 retrieval.
- `POST /api/chat`: non-streaming grounded answer.
- `POST /api/chat/stream`: server-sent streaming answer.
- `POST /api/evaluation/run`: benchmark retrieval and generation.
- `GET /metrics`: JSON runtime metrics.
- `GET /metrics/prometheus`: Prometheus-style text metrics.

## Architecture

See [docs/architecture.md](docs/architecture.md).

## Evaluation

Edit [docs/sample_eval_cases.json](docs/sample_eval_cases.json), then run:

```powershell
python scripts/benchmark.py --cases docs/sample_eval_cases.json --out data/exports/report.json
```

## Offline Guarantee

The runtime uses only local services. No OpenAI APIs or cloud inference are used. after Docker images and Ollama model weights are available on the machine, the platform can run without network access...

