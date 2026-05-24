$ErrorActionPreference = "Stop"

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
}

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

New-Item -ItemType Directory -Force -Path data, data\uploads, data\exports | Out-Null

Write-Host "Setup complete."
Write-Host "Start Qdrant: docker compose up -d qdrant"
Write-Host "Start Ollama locally or with Docker, then pull models:"
Write-Host "  ollama pull llama3"
Write-Host "  ollama pull mistral"
Write-Host "  ollama pull gemma"
Write-Host "  ollama pull deepseek-r1"
Write-Host "  ollama pull phi3"
Write-Host "  ollama pull nomic-embed-text"
Write-Host "Run app: .\.venv\Scripts\uvicorn.exe app.main:app --reload --host 127.0.0.1 --port 8000"

