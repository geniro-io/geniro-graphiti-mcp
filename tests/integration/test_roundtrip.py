"""End-to-end integration test against a real Neo4j (via testcontainers).

Marked ``integration`` — requires Docker, and an LLM/embedder the test process
can reach (set OPENAI_API_KEY, or point the env at a local Ollama). Skipped
automatically when Docker or credentials are absent so the default `pytest` run
stays hermetic.

Run explicitly with:  uv run pytest -m integration -q
"""

from __future__ import annotations

import os

import pytest

from graphiti_mcp.config import EmbedderProvider, LLMProvider, Settings
from graphiti_mcp.engine import GraphitiEngine
from graphiti_mcp.models import (
    FactSearchResponse,
    StatusResponse,
    SuccessResponse,
)
from graphiti_mcp.tools import admin, episodes, search

# Need a real LLM + embedder to extract and embed. Default to OpenAI if a key is
# present; otherwise skip (we can't fabricate embeddings).
_HAS_OPENAI = bool(os.getenv("OPENAI_API_KEY"))

try:  # Docker / testcontainers availability
    from testcontainers.neo4j import Neo4jContainer

    _HAS_TESTCONTAINERS = True
except ImportError:  # pragma: no cover
    _HAS_TESTCONTAINERS = False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _HAS_TESTCONTAINERS, reason="testcontainers/Docker not available"
    ),
    pytest.mark.skipif(
        not _HAS_OPENAI,
        reason="no OPENAI_API_KEY — integration test needs a real LLM + embedder",
    ),
]


@pytest.fixture(scope="module")
def neo4j_container():
    with Neo4jContainer("neo4j:5.26") as container:
        yield container


@pytest.fixture
async def engine(neo4j_container) -> GraphitiEngine:
    settings = Settings(
        neo4j_uri=neo4j_container.get_connection_url(),
        neo4j_user="neo4j",
        neo4j_password=neo4j_container.password,
        llm_provider=LLMProvider.OPENAI,
        llm_model=os.getenv("LLM_MODEL", "gpt-5.5"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        embedder_provider=EmbedderProvider.OPENAI,
        embedder_model="text-embedding-3-small",
        embedder_dim=1536,
        embedder_base_url=None,
        graphiti_group_id="itest",
        _env_file=None,  # type: ignore[call-arg]
    )
    eng = GraphitiEngine(settings)
    await eng.initialize()
    try:
        yield eng
    finally:
        await eng.shutdown()


async def test_add_memory_then_search_roundtrip(engine: GraphitiEngine) -> None:
    """add_memory → search_memory_facts returns the ingested fact, and the graph
    is non-empty afterwards (post-write read-back)."""
    add_result = await episodes.add_memory(
        engine,
        name="founding",
        episode_body="Alice founded Acme Corp in 2010 in Berlin.",
        source="text",
        source_description="integration test",
    )
    assert isinstance(add_result, SuccessResponse), add_result

    facts = await search.search_memory_facts(engine, "Who founded Acme Corp?", max_facts=10)
    assert isinstance(facts, FactSearchResponse), facts
    assert len(facts.facts) > 0, "expected at least one fact to be extracted"

    # Post-write read-back: confirm the graph actually has nodes.
    records, _, _ = await engine.driver.execute_query(
        "MATCH (n) RETURN count(n) AS c"
    )
    count = records[0]["c"]
    assert count > 0, "graph should be non-empty after add_memory"


async def test_get_status_reports_connected(engine: GraphitiEngine) -> None:
    status = await admin.get_status(engine)
    assert isinstance(status, StatusResponse)
    assert status.neo4j_connected is True
    assert status.status == "ok"
