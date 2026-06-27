"""Provider factories build the right client, with the #1116 guard enforced."""

from __future__ import annotations

import pytest
from graphiti_core.llm_client import OpenAIClient
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient

from graphiti_mcp.config import EmbedderProvider, LLMProvider, Settings
from graphiti_mcp.providers import (
    ProviderConfigError,
    build_embedder,
    build_llm_client,
)


def _settings(**overrides) -> Settings:
    base = dict(
        openai_api_key="sk-test",
        embedder_provider=EmbedderProvider.OPENAI,
        embedder_model="text-embedding-3-small",
        embedder_dim=1536,
        embedder_base_url=None,
        _env_file=None,
    )
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_openai_provider_uses_openai_client() -> None:
    client = build_llm_client(_settings(llm_provider=LLMProvider.OPENAI))
    assert isinstance(client, OpenAIClient)


def test_openai_generic_uses_generic_client_and_honours_base_url() -> None:
    # The #1116 guard: an OpenAI-compatible base_url MUST go through the generic
    # client, never the native one (which would ignore base_url).
    client = build_llm_client(
        _settings(
            llm_provider=LLMProvider.OPENAI_GENERIC,
            llm_base_url="http://localhost:11434/v1",
            llm_model="qwen3:8b",
        )
    )
    assert isinstance(client, OpenAIGenericClient)
    assert not isinstance(client, OpenAIClient)


def test_openai_generic_without_base_url_is_rejected() -> None:
    with pytest.raises(ProviderConfigError, match="LLM_BASE_URL"):
        build_llm_client(
            _settings(llm_provider=LLMProvider.OPENAI_GENERIC, llm_base_url=None)
        )


def test_openai_provider_without_key_is_rejected() -> None:
    with pytest.raises(ProviderConfigError, match="OPENAI_API_KEY"):
        build_llm_client(_settings(llm_provider=LLMProvider.OPENAI, openai_api_key=None))


def test_anthropic_without_key_is_rejected() -> None:
    with pytest.raises(ProviderConfigError, match="ANTHROPIC_API_KEY"):
        build_llm_client(
            _settings(llm_provider=LLMProvider.ANTHROPIC, anthropic_api_key=None)
        )


def test_embedder_openai_builds() -> None:
    emb = build_embedder(_settings(embedder_provider=EmbedderProvider.OPENAI))
    # OpenAIEmbedder — constructed without hitting the network.
    assert emb is not None


def test_embedder_ollama_requires_base_url() -> None:
    with pytest.raises(ProviderConfigError, match="EMBEDDER_BASE_URL"):
        build_embedder(
            _settings(
                embedder_provider=EmbedderProvider.OLLAMA,
                embedder_base_url=None,
            )
        )


def test_embedder_openai_requires_key() -> None:
    with pytest.raises(ProviderConfigError, match="OPENAI_API_KEY"):
        build_embedder(
            _settings(embedder_provider=EmbedderProvider.OPENAI, openai_api_key=None)
        )
