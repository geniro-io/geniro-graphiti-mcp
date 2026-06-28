"""Regression tests for the FastMCP server wrappers in :mod:`graphiti_mcp.server`.

The wrappers are the functions the MCP actually exposes; the other unit tests
exercise the tools layer directly and so never touch the thin wrapper. This file
pins the wrappers — in particular ``add_memory_bulk``, whose ``episodes``
parameter once shadowed the imported ``episodes`` tools module, making
``episodes.add_memory_bulk(...)`` resolve to the *list argument* and raise
``'list' object has no attribute 'add_memory_bulk'`` at runtime. The tools-layer
tests could not catch this because the bug lived only in the wrapper.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Iterator

import pytest

import graphiti_mcp.server as server
from graphiti_mcp.engine import GraphitiEngine
from graphiti_mcp.models import EpisodeInput


@pytest.fixture
def wired_engine(engine: GraphitiEngine) -> Iterator[GraphitiEngine]:
    """Install the mocked engine into the server module global, then restore."""
    previous = server._engine
    server._engine = engine
    try:
        yield engine
    finally:
        server._engine = previous


async def test_add_memory_bulk_wrapper_dispatches_to_tools(wired_engine, mock_client) -> None:
    """Bulk wrapper must reach the tools module, not the ``episodes`` list arg.

    Pins the module-shadowing regression: before the fix this raised
    ``AttributeError: 'list' object has no attribute 'add_memory_bulk'``.
    """
    mock_client.add_episode_bulk.return_value = SimpleNamespace(
        episodes=[1, 2], nodes=[1, 2, 3], edges=[1]
    )
    result = await server.add_memory_bulk(
        episodes=[
            EpisodeInput(name="a", episode_body="Alice joined Acme."),
            EpisodeInput(name="b", episode_body="Bob joined Acme.", source="text"),
        ],
        group_id="proj",
    )
    assert (result["episodes_added"], result["nodes_created"], result["edges_created"]) == (2, 3, 1)
    args = mock_client.add_episode_bulk.await_args
    assert len(args.args[0]) == 2
    assert args.kwargs["group_id"] == "proj"


async def test_add_memory_wrapper_dispatches_to_tools(wired_engine) -> None:
    """The aliased import must not break the single-add wrapper either."""
    result = await server.add_memory(name="n", episode_body="b")
    assert isinstance(result, dict)


async def test_add_triplet_wrapper_dispatches_to_tools(wired_engine) -> None:
    """The aliased import must not break the triplet wrapper either."""
    result = await server.add_triplet(
        source_name="A", edge_name="R", target_name="B", fact="A relates to B"
    )
    assert isinstance(result, dict)
