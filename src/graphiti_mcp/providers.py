"""LLM and embedder factories.

Two independent models are always required: a main LLM for entity/relationship
extraction and an embedder for vector search. Configuring an LLM without a
working embedder yields empty search results — so both are built here from
:class:`~graphiti_mcp.config.Settings`.

Critical correctness rule (graphiti issue #1116): the stock ``OpenAIClient``
ignores ``base_url`` and always calls api.openai.com, which 401s silently against
a LiteLLM/Ollama endpoint. Any OpenAI-compatible endpoint MUST go through
``OpenAIGenericClient`` instead. This module enforces that.
"""

from __future__ import annotations

from graphiti_core.embedder import EmbedderClient, OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client import LLMClient, LLMConfig, OpenAIClient
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient

from .config import EmbedderProvider, LLMProvider, Settings


class ProviderConfigError(ValueError):
    """Raised when provider settings are missing or inconsistent."""


def build_llm_client(settings: Settings) -> LLMClient:
    """Construct the main LLM client from settings.

    - ``openai``         → :class:`OpenAIClient` (native OpenAI).
    - ``openai_generic`` → :class:`OpenAIGenericClient` + ``LLM_BASE_URL``
      (LiteLLM / Ollama / vLLM / any OpenAI-compatible gateway).
    - ``anthropic``      → native Claude (requires the ``anthropic`` extra).
    """
    provider = settings.llm_provider

    if provider is LLMProvider.OPENAI:
        if not settings.openai_api_key:
            raise ProviderConfigError(
                "LLM_PROVIDER=openai requires OPENAI_API_KEY."
            )
        config = LLMConfig(
            api_key=settings.openai_api_key,
            model=settings.llm_model,
            small_model=settings.llm_small_model,
        )
        return OpenAIClient(config=config)

    if provider is LLMProvider.OPENAI_GENERIC:
        if not settings.llm_base_url:
            raise ProviderConfigError(
                "LLM_PROVIDER=openai_generic requires LLM_BASE_URL "
                "(e.g. http://localhost:11434/v1 for Ollama)."
            )
        config = LLMConfig(
            # Local gateways often don't check the key; send a placeholder so
            # the OpenAI SDK doesn't refuse to construct.
            api_key=settings.openai_api_key or "not-needed",
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            small_model=settings.llm_small_model,
        )
        # OpenAIGenericClient honours base_url — OpenAIClient would NOT (#1116).
        return OpenAIGenericClient(config=config)

    if provider is LLMProvider.ANTHROPIC:
        if not settings.anthropic_api_key:
            raise ProviderConfigError(
                "LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY."
            )
        try:
            from graphiti_core.llm_client.anthropic_client import AnthropicClient
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise ProviderConfigError(
                "LLM_PROVIDER=anthropic needs the 'anthropic' extra. "
                "Install with: uv pip install 'geniro-graphiti-mcp[anthropic]'."
            ) from exc
        config = LLMConfig(
            api_key=settings.anthropic_api_key,
            model=settings.llm_model,
            small_model=settings.llm_small_model,
        )
        return AnthropicClient(config=config)

    raise ProviderConfigError(f"Unsupported LLM_PROVIDER: {provider!r}")


def build_embedder(settings: Settings) -> EmbedderClient:
    """Construct the embedder client from settings.

    OpenAI, Ollama and any OpenAI-compatible endpoint all use
    :class:`OpenAIEmbedder`; the base_url selects the backend. Voyage uses its
    own client (requires the ``voyage`` extra).

    Note: the configured model MUST be an *embedding* model (e.g.
    ``qwen3-embedding:8b``), never a chat model, and ``EMBEDDER_DIM`` must match
    its output dimension — otherwise search silently returns nothing.
    """
    provider = settings.embedder_provider

    if provider is EmbedderProvider.VOYAGE:
        if not settings.voyage_api_key:
            raise ProviderConfigError(
                "EMBEDDER_PROVIDER=voyage requires VOYAGE_API_KEY."
            )
        try:
            from graphiti_core.embedder.voyage import (
                VoyageAIEmbedder,
                VoyageAIEmbedderConfig,
            )
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise ProviderConfigError(
                "EMBEDDER_PROVIDER=voyage needs the 'voyage' extra. "
                "Install with: uv pip install 'geniro-graphiti-mcp[voyage]'."
            ) from exc
        return VoyageAIEmbedder(
            config=VoyageAIEmbedderConfig(
                api_key=settings.voyage_api_key,
                embedding_model=settings.embedder_model,
                embedding_dim=settings.embedder_dim,
            )
        )

    # openai / ollama / openai_generic → OpenAIEmbedder (base_url-driven).
    base_url = settings.embedder_base_url
    if provider in (EmbedderProvider.OLLAMA, EmbedderProvider.OPENAI_GENERIC) and not base_url:
        raise ProviderConfigError(
            f"EMBEDDER_PROVIDER={provider.value} requires EMBEDDER_BASE_URL."
        )
    if provider is EmbedderProvider.OPENAI:
        # Native OpenAI: ignore any stray base_url and require the key.
        base_url = None
        if not settings.resolved_embedder_api_key:
            raise ProviderConfigError(
                "EMBEDDER_PROVIDER=openai requires OPENAI_API_KEY "
                "(or EMBEDDER_API_KEY)."
            )

    config = OpenAIEmbedderConfig(
        api_key=settings.resolved_embedder_api_key or "not-needed",
        embedding_model=settings.embedder_model,
        embedding_dim=settings.embedder_dim,
        base_url=base_url,
    )
    return OpenAIEmbedder(config=config)
