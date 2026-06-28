"""Shared test fixtures."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from graphiti_mcp.config import EmbedderProvider, LLMProvider, Settings
from graphiti_mcp.engine import GraphitiEngine


@pytest.fixture
def settings() -> Settings:
    """Deterministic settings that never read the developer's real environment."""
    return Settings(
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="test",
        llm_provider=LLMProvider.OPENAI,
        llm_model="gpt-5.5",
        openai_api_key="sk-test",
        embedder_provider=EmbedderProvider.OPENAI,
        embedder_model="text-embedding-3-small",
        embedder_dim=1536,
        embedder_base_url=None,
        graphiti_group_id="main",
        _env_file=None,  # type: ignore[call-arg]
    )


@pytest.fixture
def mock_client() -> AsyncMock:
    """A stand-in for a live graphiti_core.Graphiti instance."""
    return AsyncMock()


@pytest.fixture
def engine(settings: Settings, mock_client: AsyncMock) -> GraphitiEngine:
    """A GraphitiEngine whose Graphiti client is mocked (no Neo4j needed)."""
    eng = GraphitiEngine(settings)
    eng._graphiti = mock_client  # type: ignore[attr-defined]
    # Skip the lazy embedder-dim probe by default — tests that exercise it set
    # this back to False and stub `mock_client.embedder.create`.
    eng._embedder_checked = True  # type: ignore[attr-defined]
    return eng
