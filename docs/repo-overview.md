# Repository Overview

Private Research Copilot is a local-first document research application. It combines a FastAPI service and browser dashboard with Ollama for local language models, Qdrant for vector search, and SQLite for document metadata, conversation history, and BM25 full-text search.

## How It Works

1. A user uploads a supported document or submits a local path for ingestion.
2. The ingestion pipeline loads and chunks the document, requests embeddings from Ollama, and stores chunk metadata in SQLite and vectors in Qdrant.
3. A search or chat request retrieves relevant chunks using vector search and SQLite full-text search.
4. The generation service sends retrieved context to Ollama and returns a grounded answer with citations. Conversation history is stored in SQLite.

## Where to Find Things

| Path | Responsibility |
| --- | --- |
| `app/main.py` | FastAPI application setup, service construction, and lifespan management. |
| `app/api/` | HTTP endpoints for chat, evaluation, health, ingestion, models, and retrieval. |
| `app/core/` | Configuration, Ollama client, logging, metrics, and background task queue. |
| `app/db/repository.py` | SQLite schema and persistence operations. |
| `app/ingestion/` | Document loading, chunking, and the ingestion pipeline. |
| `app/retrieval/` | Qdrant vector store, hybrid search, query handling, and reranking. |
| `app/generation/` | Retrieval-augmented answer generation. |
| `app/evaluation/` | Evaluation metrics and report generation. |
| `app/models/` | Pydantic request and response schemas. |
| `app/static/` | Browser dashboard HTML, CSS, and JavaScript. |
| `data/` | Local database, uploaded documents, and generated exports. |
| `docs/` | Architecture, deployment, evaluation guidance, and sample evaluation cases. |
| `scripts/` | Setup and benchmark utilities. |
| `tests/` | Unit tests for chunking and repository behavior. |

For the component diagram and extension points, see [Architecture](architecture.md). For environment-specific startup instructions, see [Deployment](deployment.md).

## Data and Services

- SQLite defaults to `data/research_copilot.db` and stores metadata, chunks, conversations, messages, ingestion jobs, and evaluation reports.
- Uploaded files default to `data/uploads`; benchmark exports default to `data/exports`.
- Qdrant stores vectors in the Docker volume `qdrant_data` when using Compose.
- Ollama model files are stored by the local Ollama installation or in the Compose volume `ollama_data`.
- Compose runs the app, Qdrant, and Ollama. The app's `data/` directory is bind-mounted from the repository; `docs/` is mounted read-only.

## Run Locally

From the repository root in PowerShell:

```powershell
copy .env.example .env
.\scripts\setup.ps1
docker compose up -d qdrant
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. This mode uses a locally installed Ollama service. To run the complete stack in Docker instead, use `docker compose up --build`; see [Deployment](deployment.md).

## Tests and Useful Endpoints

Run the test suite with:

```powershell
pytest
```

The API includes document upload and path ingestion under `/api/ingest`, search under `/api/search`, chat under `/api/chat`, and evaluation under `/api/evaluation`. The root URL serves the dashboard, and `/docs` serves the FastAPI interactive API documentation.