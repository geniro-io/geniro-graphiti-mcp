"""Settings load correctly from the environment."""

from __future__ import annotations

from graphiti_mcp.config import EmbedderProvider, LLMProvider, Settings


def test_defaults_describe_local_recommended_setup() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.llm_provider is LLMProvider.OPENAI
    assert s.llm_model == "gpt-5.5"
    assert s.embedder_provider is EmbedderProvider.OLLAMA
    assert s.embedder_model == "qwen3-embedding:8b"
    assert s.embedder_dim == 4096
    assert s.graphiti_group_id == "main"


def test_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_MODEL", "claude-sonnet-4-6")
    monkeypatch.setenv("EMBEDDER_DIM", "768")
    monkeypatch.setenv("GRAPHITI_GROUP_ID", "project-x")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.llm_provider is LLMProvider.ANTHROPIC
    assert s.llm_model == "claude-sonnet-4-6"
    assert s.embedder_dim == 768
    assert s.graphiti_group_id == "project-x"


def test_embedder_api_key_falls_back_to_openai_key() -> None:
    s = Settings(openai_api_key="sk-main", embedder_api_key=None, _env_file=None)  # type: ignore[call-arg]
    assert s.resolved_embedder_api_key == "sk-main"
    s2 = Settings(openai_api_key="sk-main", embedder_api_key="sk-emb", _env_file=None)  # type: ignore[call-arg]
    assert s2.resolved_embedder_api_key == "sk-emb"
