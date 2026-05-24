from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Private Research Copilot"
    env: str = "local"
    log_level: str = "INFO"

    database_path: Path = Path("data/research_copilot.db")
    upload_dir: Path = Path("data/uploads")
    export_dir: Path = Path("data/exports")

    ollama_base_url: str = "http://localhost:11434"
    chat_models: str = "llama3,mistral,gemma,deepseek-r1,phi3"
    default_chat_model: str = "llama3"
    embedding_model: str = "nomic-embed-text"

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection_prefix: str = "private_research"

    chunk_size: int = Field(default=900, ge=200, le=4000)
    chunk_overlap: int = Field(default=160, ge=0, le=1000)
    default_top_k: int = Field(default=6, ge=1, le=50)
    hybrid_alpha: float = Field(default=0.62, ge=0.0, le=1.0)
    vector_expansion_factor: int = Field(default=4, ge=1, le=10)
    max_context_chars: int = Field(default=12_000, ge=2_000, le=64_000)
    recent_messages: int = Field(default=8, ge=0, le=30)
    request_timeout_s: float = Field(default=120.0, ge=5.0)

    enable_query_decomposition: bool = True
    enable_contextual_compression: bool = True
    task_retries: int = Field(default=2, ge=0, le=10)

    model_config = SettingsConfigDict(env_file=".env", env_prefix="PRC_", extra="ignore")

    @property
    def configured_chat_models(self) -> list[str]:
        return [model.strip() for model in self.chat_models.split(",") if model.strip()]

    @property
    def root_dir(self) -> Path:
        return Path(__file__).resolve().parents[2]

    @property
    def static_dir(self) -> Path:
        return self.root_dir / "app" / "static"

    def ensure_directories(self) -> None:
        for directory in (self.database_path.parent, self.upload_dir, self.export_dir):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings

