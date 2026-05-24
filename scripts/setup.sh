#!/usr/bin/env bash
set -euo pipefail

if [ ! -f ".env" ]; then
  cp .env.example .env
fi

python -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements-dev.txt

mkdir -p data/uploads data/exports

cat <<'EOF'
Setup complete.
Start Qdrant: docker compose up -d qdrant
Start Ollama locally or with Docker, then pull models:
  ollama pull llama3
  ollama pull mistral
  ollama pull gemma
  ollama pull deepseek-r1
  ollama pull phi3
  ollama pull nomic-embed-text
Run app: ./.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
EOF

