FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PRC_DATABASE_PATH=/app/data/research_copilot.db \
    PRC_UPLOAD_DIR=/app/data/uploads \
    PRC_EXPORT_DIR=/app/data/exports \
    PRC_QDRANT_URL=http://qdrant:6333 \
    PRC_OLLAMA_BASE_URL=http://ollama:11434

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app app
COPY docs docs
COPY scripts scripts
COPY README.md .

RUN mkdir -p /app/data/uploads /app/data/exports

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

