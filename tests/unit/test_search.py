"""Search tools call the engine correctly and format results."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from graphiti_mcp.models import ErrorResponse, FactSearchResponse, NodeSearchResponse
from graphiti_mcp.tools import search


# SimpleNamespace (not Mock) because `name` is reserved by Mock and would return
# a child mock instead of the string.
def _edge(uuid: str, fact: str) -> SimpleNamespace:
    return SimpleNamespace(
        uuid=uuid,
        fact=fact,
        name="REL",
        source_node_uuid="s",
        target_node_uuid="t",
        group_id="main",
        valid_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        invalid_at=None,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _node(uuid: str, name: str) -> SimpleNamespace:
    return SimpleNamespace(
        uuid=uuid,
        name=name,
        summary="a summary",
        labels=["Entity"],
        group_id="main",
        attributes={"k": "v"},
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


async def test_search_memory_facts_formats_edges(engine, mock_client) -> None:
    mock_client.search.return_value = [_edge("e1", "Alice knows Bob")]
    result = await search.search_memory_facts(engine, "who does Alice know")
    assert isinstance(result, FactSearchResponse)
    assert len(result.facts) == 1
    assert result.facts[0].fact == "Alice knows Bob"
    assert mock_client.search.await_args.kwargs["group_ids"] == ["main"]


async def test_search_memory_facts_propagates_failure(engine, mock_client) -> None:
    mock_client.search.side_effect = RuntimeError("boom")
    result = await search.search_memory_facts(engine, "q")
    assert isinstance(result, ErrorResponse)
    assert "boom" in result.error


async def test_search_memory_facts_rejects_nonpositive_limit(engine, mock_client) -> None:
    result = await search.search_memory_facts(engine, "q", max_facts=0)
    assert isinstance(result, ErrorResponse)
    mock_client.search.assert_not_called()


async def test_search_nodes_formats_nodes_and_sets_limit(engine, mock_client) -> None:
    mock_client.search_.return_value = Mock(nodes=[_node("n1", "Alice")])
    result = await search.search_nodes(engine, "find Alice", max_nodes=5)
    assert isinstance(result, NodeSearchResponse)
    assert result.nodes[0].name == "Alice"
    # The recipe's limit is overridden with max_nodes (copied, not mutated global).
    assert mock_client.search_.await_args.kwargs["config"].limit == 5


async def test_search_nodes_does_not_mutate_global_recipe(engine, mock_client) -> None:
    from graphiti_core.search.search_config_recipes import NODE_HYBRID_SEARCH_RRF

    original_limit = NODE_HYBRID_SEARCH_RRF.limit
    mock_client.search_.return_value = Mock(nodes=[])
    await search.search_nodes(engine, "q", max_nodes=99)
    assert NODE_HYBRID_SEARCH_RRF.limit == original_limit


async def test_search_nodes_propagates_failure(engine, mock_client) -> None:
    mock_client.search_.side_effect = RuntimeError("nope")
    result = await search.search_nodes(engine, "q")
    assert isinstance(result, ErrorResponse)
