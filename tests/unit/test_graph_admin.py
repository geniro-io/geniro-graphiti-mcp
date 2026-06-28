"""Retrieval/deletion and admin tools: call-through + error propagation + status."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from graphiti_mcp.engine import EngineNotInitializedError, GraphitiEngine
from graphiti_mcp.models import (
    EpisodeListResponse,
    ErrorResponse,
    FactResponse,
    NodeSearchResponse,
    StatusResponse,
    SuccessResponse,
)
from graphiti_mcp.tools import admin, graph


# ── retrieval / deletion ──────────────────────────────────────────────────


async def test_get_episodes_formats(engine, mock_client) -> None:
    ep = SimpleNamespace(
        uuid="ep1",
        name="note",
        content="hi",
        source=SimpleNamespace(value="message"),
        source_description="chat",
        group_id="main",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    mock_client.retrieve_episodes.return_value = [ep]
    result = await graph.get_episodes(engine, last_n=3)
    assert isinstance(result, EpisodeListResponse)
    assert result.episodes[0].source == "message"


async def test_get_episodes_rejects_nonpositive(engine) -> None:
    result = await graph.get_episodes(engine, last_n=0)
    assert isinstance(result, ErrorResponse)


async def test_get_episodes_propagates_failure(engine, mock_client) -> None:
    mock_client.retrieve_episodes.side_effect = RuntimeError("db error")
    result = await graph.get_episodes(engine, last_n=5)
    assert isinstance(result, ErrorResponse)
    assert "db error" in result.error


async def test_get_episode_entities_formats_nodes(engine, mock_client) -> None:
    node = SimpleNamespace(
        uuid="n1", name="Alice", summary="", labels=["Entity"],
        group_id="main", attributes={}, created_at=None,
    )
    mock_client.get_nodes_and_edges_by_episode.return_value = SimpleNamespace(nodes=[node])
    result = await graph.get_episode_entities(engine, "ep-1")
    assert isinstance(result, NodeSearchResponse)
    assert result.nodes[0].name == "Alice"
    mock_client.get_nodes_and_edges_by_episode.assert_awaited_once_with(["ep-1"])


async def test_get_episode_entities_handles_empty(engine, mock_client) -> None:
    mock_client.get_nodes_and_edges_by_episode.return_value = SimpleNamespace(nodes=[])
    result = await graph.get_episode_entities(engine, "ep-1")
    assert isinstance(result, NodeSearchResponse)
    assert result.nodes == []


async def test_get_episode_entities_propagates_failure(engine, mock_client) -> None:
    mock_client.get_nodes_and_edges_by_episode.side_effect = RuntimeError("boom")
    result = await graph.get_episode_entities(engine, "ep-1")
    assert isinstance(result, ErrorResponse)
    assert "boom" in result.error


async def test_delete_entity_edge_propagates_failure(engine) -> None:
    with patch(
        "graphiti_mcp.tools.graph.EntityEdge.get_by_uuid",
        new=AsyncMock(side_effect=RuntimeError("not found")),
    ):
        result = await graph.delete_entity_edge(engine, "missing-uuid")
    assert isinstance(result, ErrorResponse)
    assert "not found" in result.error


async def test_delete_entity_edge_success(engine) -> None:
    edge = AsyncMock()
    with patch(
        "graphiti_mcp.tools.graph.EntityEdge.get_by_uuid",
        new=AsyncMock(return_value=edge),
    ):
        result = await graph.delete_entity_edge(engine, "uuid-1")
    assert isinstance(result, SuccessResponse)
    edge.delete.assert_awaited_once()


async def test_get_entity_edge_formats(engine) -> None:
    edge = SimpleNamespace(
        uuid="e1", fact="a fact", name="REL", source_node_uuid="s",
        target_node_uuid="t", group_id="main", valid_at=None, invalid_at=None,
        created_at=None,
    )
    with patch(
        "graphiti_mcp.tools.graph.EntityEdge.get_by_uuid",
        new=AsyncMock(return_value=edge),
    ):
        result = await graph.get_entity_edge(engine, "e1")
    # Wrapped in the uniform status envelope (FactResponse), like every other tool.
    assert isinstance(result, FactResponse)
    assert result.status == "success"
    assert result.fact.fact == "a fact"


async def test_delete_episode_uses_remove_episode(engine, mock_client) -> None:
    result = await graph.delete_episode(engine, "ep-1")
    assert isinstance(result, SuccessResponse)
    mock_client.remove_episode.assert_awaited_once_with("ep-1")


async def test_delete_episode_propagates_failure(engine, mock_client) -> None:
    mock_client.remove_episode.side_effect = RuntimeError("delete failed")
    result = await graph.delete_episode(engine, "ep-1")
    assert isinstance(result, ErrorResponse)
    assert "delete failed" in result.error


# ── admin ──────────────────────────────────────────────────────────────────


async def test_build_communities_reports_count(engine, mock_client) -> None:
    mock_client.build_communities.return_value = ([Mock(), Mock()], [])
    result = await admin.build_communities(engine)
    assert isinstance(result, SuccessResponse)
    assert "2 communities" in result.message


async def test_build_communities_propagates_failure(engine, mock_client) -> None:
    mock_client.build_communities.side_effect = RuntimeError("algo failed")
    result = await admin.build_communities(engine)
    assert isinstance(result, ErrorResponse)
    assert "algo failed" in result.error


async def test_clear_graph_is_group_scoped(engine, mock_client) -> None:
    with patch(
        "graphiti_mcp.tools.admin.clear_data", new=AsyncMock()
    ) as clear_data:
        result = await admin.clear_graph(engine, group_id="proj")
    assert isinstance(result, SuccessResponse)
    # Scoped to exactly the requested group — never a global wipe.
    assert clear_data.await_args.kwargs["group_ids"] == ["proj"]
    mock_client.build_indices_and_constraints.assert_awaited()


async def test_clear_graph_propagates_failure(engine, mock_client) -> None:
    with patch(
        "graphiti_mcp.tools.admin.clear_data",
        new=AsyncMock(side_effect=RuntimeError("wipe failed")),
    ):
        result = await admin.clear_graph(engine, group_id="proj")
    assert isinstance(result, ErrorResponse)
    assert "wipe failed" in result.error


async def test_summarize_saga_returns_summary(engine, mock_client) -> None:
    mock_client.summarize_saga.return_value = Mock(summary="the saga so far")
    result = await admin.summarize_saga(engine, "saga-1")
    assert isinstance(result, SuccessResponse)
    assert result.message == "the saga so far"


async def test_summarize_saga_propagates_failure(engine, mock_client) -> None:
    mock_client.summarize_saga.side_effect = RuntimeError("summary failed")
    result = await admin.summarize_saga(engine, "saga-1")
    assert isinstance(result, ErrorResponse)
    assert "summary failed" in result.error


async def test_summarize_saga_empty_summary_uses_fallback(engine, mock_client) -> None:
    # graphiti returns a saga with no usable summary → user-visible placeholder.
    mock_client.summarize_saga.return_value = SimpleNamespace(summary="")
    result = await admin.summarize_saga(engine, "saga-1")
    assert isinstance(result, SuccessResponse)
    assert result.message == "(no summary produced)"


async def test_get_status_healthy(engine, mock_client) -> None:
    mock_client.driver.execute_query = AsyncMock(return_value=None)
    result = await admin.get_status(engine)
    assert isinstance(result, StatusResponse)
    assert result.neo4j_connected is True
    assert result.status == "ok"
    assert result.llm_model == "gpt-5.5"
    # No workspace configured (only graphiti_group_id="main"): workspace reports
    # empty truthfully, while group_id is the effective namespace.
    assert result.workspace == ""
    assert result.group_id == "main"


async def test_get_status_reports_configured_workspace(engine, mock_client) -> None:
    engine.settings.workspace = "project-b"
    mock_client.driver.execute_query = AsyncMock(return_value=None)
    result = await admin.get_status(engine)
    assert result.workspace == "project-b"
    assert result.group_id == "project-b"


async def test_get_status_degraded_when_neo4j_down(engine, mock_client) -> None:
    mock_client.driver.execute_query = AsyncMock(side_effect=OSError("refused"))
    result = await admin.get_status(engine)
    assert result.neo4j_connected is False
    assert result.status == "degraded"


# ── engine guard ────────────────────────────────────────────────────────────


def test_engine_client_raises_before_initialize(settings) -> None:
    # Using a tool before the lifespan initialized the engine must raise, not
    # silently operate on a None client.
    eng = GraphitiEngine(settings)
    with pytest.raises(EngineNotInitializedError):
        _ = eng.client
