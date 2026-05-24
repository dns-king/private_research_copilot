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

```bash
copy .env.example .env
docker compose up --build
```

The dashboard is available at `http://127.0.0.1:8000`.

## Offline Operation

After Docker images and Ollama models are present locally, the system does not call external APIs. Document text, embeddings, vectors, metadata, prompts, and generated answers remain on the machine.

