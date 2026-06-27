"""Environment-driven configuration.

All settings come from environment variables (or a local ``.env``); there is no
YAML layer. The defaults describe the recommended local setup: OpenAI ``gpt-5.5``
for extraction and a local Ollama ``qwen3-embedding:8b`` embedder.
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(str, Enum):
    """Main-LLM backend selector (entity/relationship extraction)."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    # Any OpenAI-compatible endpoint reached via LLM_BASE_URL: LiteLLM, Ollama,
    # vLLM, OpenRouter, etc. Uses OpenAIGenericClient so base_url is honoured.
    OPENAI_GENERIC = "openai_generic"


class EmbedderProvider(str, Enum):
    """Embedder backend selector (vector embeddings)."""

    OPENAI = "openai"
    # Ollama is just an OpenAI-compatible endpoint; kept as a distinct value so
    # the default config reads clearly.
    OLLAMA = "ollama"
    VOYAGE = "voyage"
    OPENAI_GENERIC = "openai_generic"


class Settings(BaseSettings):
    """Resolved server configuration, read once at startup.

    Field names map to upper-cased env vars case-insensitively
    (e.g. ``neo4j_uri`` ← ``NEO4J_URI``).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Neo4j ────────────────────────────────────────────────────────
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "demodemo"
    neo4j_database: str = "neo4j"

    # ── Main LLM ─────────────────────────────────────────────────────
    llm_provider: LLMProvider = LLMProvider.OPENAI
    llm_model: str = "gpt-5.5"
    llm_base_url: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    # Optional secondary "small" model graphiti-core uses for cheap calls.
    llm_small_model: str | None = None

    # ── Embedder ─────────────────────────────────────────────────────
    embedder_provider: EmbedderProvider = EmbedderProvider.OLLAMA
    embedder_model: str = "qwen3-embedding:8b"
    embedder_dim: int = 4096
    embedder_base_url: str | None = "http://localhost:11434/v1"
    # Falls back to ``openai_api_key`` when unset (handy for OpenAI embedder).
    embedder_api_key: str | None = None
    voyage_api_key: str | None = None

    # ── Graphiti behaviour ───────────────────────────────────────────
    # Optional namespacing for memories — not a security boundary.
    graphiti_group_id: str = Field(default="main")
    # Concurrency cap for graphiti-core's internal coroutines.
    semaphore_limit: int = 10

    @property
    def resolved_embedder_api_key(self) -> str | None:
        """Embedder key, defaulting to the OpenAI key for OpenAI-style endpoints."""
        return self.embedder_api_key or self.openai_api_key


def load_settings() -> Settings:
    """Read settings from the environment / ``.env``."""
    return Settings()
