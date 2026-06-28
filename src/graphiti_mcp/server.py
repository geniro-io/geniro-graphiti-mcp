"""FastMCP server: lifecycle wiring, tool registration, stdio entrypoint.

The engine is created and indices are built in the lifespan startup, and the
driver is closed on shutdown. Each ``@mcp.tool`` is a thin wrapper that calls the
corresponding function in :mod:`graphiti_mcp.tools` with the live engine and
returns a JSON-serializable dict.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from mcp.server.fastmcp import FastMCP

from .config import load_settings
from .engine import EngineNotInitializedError, GraphitiEngine
from .models import EpisodeInput
from .tools import admin, episodes as episode_tools, graph, groups, search

logger = logging.getLogger(__name__)

# Module-level engine, populated by the lifespan and read by the tool wrappers.
_engine: GraphitiEngine | None = None


def get_engine() -> GraphitiEngine:
    if _engine is None:
        raise EngineNotInitializedError("Server lifespan has not started the engine.")
    return _engine


@asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[None]:
    """Build the engine + indices on startup; close the driver on shutdown."""
    global _engine
    settings = load_settings()
    engine = GraphitiEngine(settings)
    try:
        # initialize() is awaited inside the try so a startup failure (bad creds,
        # index build error) still triggers shutdown() — closing any driver it
        # opened — and never leaves a half-built engine in the module global.
        await engine.initialize()
        _engine = engine
        yield
    finally:
        await engine.shutdown()
        _engine = None


mcp = FastMCP(
    "graphiti",
    instructions=(
        "Graphiti knowledge-graph memory. Use add_memory to ingest information "
        "(it is persisted synchronously — a failure is reported immediately, not "
        "silently dropped), and search_memory_facts / search_nodes to recall it."
    ),
    lifespan=lifespan,
)


# ── Ingestion ────────────────────────────────────────────────────────────


@mcp.tool()
async def add_memory(
    name: str,
    episode_body: str,
    source: Literal["message", "text", "json"] = "message",
    source_description: str = "",
    group_id: str | None = None,
    reference_time: str | None = None,
    uuid: str | None = None,
) -> dict:
    """Add a memory (episode) to the knowledge graph and wait for it to persist.

    Args:
        name: Short human label for the episode.
        episode_body: The content; for ``source="json"`` pass a JSON string.
        source: One of ``"message"`` | ``"text"`` | ``"json"``.
        source_description: Provenance note (e.g. "user chat").
        group_id: Memory namespace (workspace); defaults to the configured one.
        reference_time: ISO-8601 timestamp; defaults to now (UTC).
        uuid: Optional explicit episode UUID for idempotent re-ingest.

    Returns success only after the write completes; on failure returns an error.
    """
    result = await episode_tools.add_memory(
        get_engine(),
        name=name,
        episode_body=episode_body,
        source=source,
        source_description=source_description,
        group_id=group_id,
        reference_time=reference_time,
        uuid=uuid,
    )
    return result.model_dump()


@mcp.tool()
async def add_memory_bulk(
    episodes: list[EpisodeInput],
    group_id: str | None = None,
) -> dict:
    """Add many memories (episodes) in one batched, awaited operation.

    Faster than calling add_memory repeatedly (the batch is extracted, embedded
    and deduplicated together); still synchronous, so failures are reported, not
    dropped. Each item: name, episode_body, and optional source
    ("message"|"text"|"json"), source_description, reference_time (ISO-8601), uuid.
    """
    result = await episode_tools.add_memory_bulk(get_engine(), episodes, group_id=group_id)
    return result.model_dump()


@mcp.tool()
async def add_triplet(
    source_name: str,
    edge_name: str,
    target_name: str,
    fact: str,
    group_id: str | None = None,
) -> dict:
    """Add an explicit (source)-[edge]->(target) fact triplet."""
    result = await episode_tools.add_triplet(
        get_engine(),
        source_name=source_name,
        edge_name=edge_name,
        target_name=target_name,
        fact=fact,
        group_id=group_id,
    )
    return result.model_dump()


# ── Search ────────────────────────────────────────────────────────────────


@mcp.tool()
async def search_memory_facts(
    query: str,
    max_facts: int = 10,
    group_id: str | None = None,
) -> dict:
    """Search for relationships (facts) relevant to a query."""
    result = await search.search_memory_facts(
        get_engine(), query, max_facts=max_facts, group_id=group_id
    )
    return result.model_dump()


@mcp.tool()
async def search_nodes(
    query: str,
    max_nodes: int = 10,
    group_id: str | None = None,
) -> dict:
    """Search for entity nodes relevant to a query."""
    result = await search.search_nodes(
        get_engine(), query, max_nodes=max_nodes, group_id=group_id
    )
    return result.model_dump()


# ── Retrieval / deletion ───────────────────────────────────────────────────


@mcp.tool()
async def get_episodes(last_n: int = 10, group_id: str | None = None) -> dict:
    """Return the most recent episodes for a group."""
    result = await graph.get_episodes(get_engine(), last_n=last_n, group_id=group_id)
    return result.model_dump()


@mcp.tool()
async def get_episode_entities(episode_uuid: str) -> dict:
    """Return the entity nodes extracted from a given episode."""
    result = await graph.get_episode_entities(get_engine(), episode_uuid)
    return result.model_dump()


@mcp.tool()
async def get_entity_edge(uuid: str) -> dict:
    """Return a single relationship edge by UUID."""
    result = await graph.get_entity_edge(get_engine(), uuid)
    return result.model_dump()


@mcp.tool()
async def delete_entity_edge(uuid: str) -> dict:
    """Delete a relationship edge by UUID."""
    result = await graph.delete_entity_edge(get_engine(), uuid)
    return result.model_dump()


@mcp.tool()
async def delete_episode(episode_uuid: str) -> dict:
    """Delete an episode (and its derived graph data) by UUID."""
    result = await graph.delete_episode(get_engine(), episode_uuid)
    return result.model_dump()


# ── Admin ──────────────────────────────────────────────────────────────────


@mcp.tool()
async def list_group_ids() -> dict:
    """List the distinct group_ids (memory namespaces) present in the graph."""
    result = await groups.list_group_ids(get_engine())
    return result.model_dump()


@mcp.tool()
async def build_communities(group_id: str | None = None) -> dict:
    """(Re)build community clusters for a group."""
    result = await admin.build_communities(get_engine(), group_id=group_id)
    return result.model_dump()


@mcp.tool()
async def summarize_saga(saga_id: str) -> dict:
    """Summarize a saga (a thread of related episodes)."""
    result = await admin.summarize_saga(get_engine(), saga_id)
    return result.model_dump()


@mcp.tool()
async def clear_graph(group_id: str | None = None) -> dict:
    """DESTRUCTIVE: delete all graph data for a single group, then rebuild indices."""
    result = await admin.clear_graph(get_engine(), group_id=group_id)
    return result.model_dump()


@mcp.tool()
async def get_status() -> dict:
    """Report Neo4j connectivity and the resolved LLM/embedder providers."""
    result = await admin.get_status(get_engine())
    return result.model_dump()


def main() -> None:
    """Console-script entrypoint: run the MCP server over stdio."""
    # Logs MUST go to stderr — stdout is the MCP transport on stdio.
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
