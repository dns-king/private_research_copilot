# Deployment

## Local Python

```bash
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Start Qdrant separately:

```bash
docker compose up -d qdrant
```

Start Ollama and pull local models:

```bash
ollama pull llama3
ollama pull mistral
ollama pull gemma
ollama pull deepseek-r1
ollama pull phi3
ollama pull nomic-embed-text
```

## Docker Compose

Run these commands from the repository root. The Compose file uses the published app image; it does not build the app locally.

```bash
copy .env.example .env
docker compose pull
docker compose up -d
docker compose exec ollama ollama pull llama3
docker compose exec ollama ollama pull nomic-embed-text
```

The dashboard is available at `http://127.0.0.1:8000`. The default chat and embedding models must be downloaded into Ollama before chat or document ingestion will work. Other selectable chat models configured in `.env` must also be pulled before use.

Use `docker compose logs -f app` to inspect app logs and `docker compose down` to stop the stack. App data is stored under `data/`; Qdrant vectors and Ollama models are kept in named Docker volumes.

## Offline Operation

After Docker images and Ollama models are present locally, the system does not call external APIs. Document text, embeddings, vectors, metadata, prompts, and generated answers remain on the machine.

