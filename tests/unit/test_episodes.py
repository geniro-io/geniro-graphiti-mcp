"""The core guarantee: a failed write returns an error synchronously.

These tests encode the entire reason this rewrite exists — there is no queue, so
``add_memory`` cannot return success while the write fails in the background.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from graphiti_mcp.models import ErrorResponse, SuccessResponse
from graphiti_mcp.tools import episodes


async def test_add_memory_success(engine, mock_client) -> None:
    mock_client.add_episode.return_value = Mock(episode=Mock(uuid="ep-123"))

    result = await episodes.add_memory(engine, name="note", episode_body="hello")

    assert isinstance(result, SuccessResponse)
    assert result.status == "success"
    assert "ep-123" in result.message
    mock_client.add_episode.assert_awaited_once()


async def test_add_memory_propagates_failure_as_error_not_success(engine, mock_client) -> None:
    # THE anti-silent-drop test: the write raises ...
    mock_client.add_episode.side_effect = RuntimeError("neo4j unreachable")

    result = await episodes.add_memory(engine, name="note", episode_body="hello")

    # ... and the caller gets an ErrorResponse in the SAME call — never a success.
    assert isinstance(result, ErrorResponse)
    assert result.status == "error"
    assert "neo4j unreachable" in result.error
    assert not isinstance(result, SuccessResponse)


async def test_add_memory_awaits_the_write(engine, mock_client) -> None:
    # The write must actually be awaited (not enqueued-and-forgotten).
    mock_client.add_episode.return_value = Mock(episode=Mock(uuid="ep-1"))
    await episodes.add_memory(engine, name="n", episode_body="b")
    mock_client.add_episode.assert_awaited_once()


async def test_add_memory_passes_default_group_id(engine, mock_client) -> None:
    mock_client.add_episode.return_value = Mock(episode=Mock(uuid="ep-1"))
    await episodes.add_memory(engine, name="n", episode_body="b")
    kwargs = mock_client.add_episode.await_args.kwargs
    assert kwargs["group_id"] == "main"


async def test_add_memory_explicit_group_id_overrides(engine, mock_client) -> None:
    mock_client.add_episode.return_value = Mock(episode=Mock(uuid="ep-1"))
    await episodes.add_memory(engine, name="n", episode_body="b", group_id="other")
    assert mock_client.add_episode.await_args.kwargs["group_id"] == "other"


async def test_add_memory_uses_configured_workspace(engine, mock_client) -> None:
    # When a workspace is configured, ingests land in it by default.
    engine.settings.workspace = "project-a"
    mock_client.add_episode.return_value = Mock(episode=Mock(uuid="ep-1"))
    await episodes.add_memory(engine, name="n", episode_body="b")
    assert mock_client.add_episode.await_args.kwargs["group_id"] == "project-a"


async def test_add_memory_forwards_reference_time_and_uuid(engine, mock_client) -> None:
    # A valid ISO timestamp is parsed and forwarded, and the idempotency uuid
    # passes through — neither is silently dropped.
    mock_client.add_episode.return_value = Mock(episode=Mock(uuid="ep-1"))
    await episodes.add_memory(
        engine, name="n", episode_body="b",
        reference_time="2026-01-02T03:04:05+00:00", uuid="ep-x",
    )
    kwargs = mock_client.add_episode.await_args.kwargs
    assert kwargs["uuid"] == "ep-x"
    assert kwargs["reference_time"] == datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


async def test_add_memory_naive_reference_time_normalized_to_utc(engine, mock_client) -> None:
    mock_client.add_episode.return_value = Mock(episode=Mock(uuid="ep-1"))
    await episodes.add_memory(
        engine, name="n", episode_body="b", reference_time="2026-01-02T03:04:05"
    )
    ref = mock_client.add_episode.await_args.kwargs["reference_time"]
    assert ref.tzinfo is not None
    assert ref == datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


async def test_add_memory_surfaces_embedder_dim_mismatch_as_error(engine, mock_client) -> None:
    # A wrong EMBEDDER_DIM is caught on the first ingest as a synchronous error,
    # not a false success that yields empty search later (spec risk-5).
    engine._embedder_checked = False  # type: ignore[attr-defined]
    mock_client.embedder.create = AsyncMock(return_value=[0.0] * 512)  # configured dim is 1536
    result = await episodes.add_memory(engine, name="n", episode_body="b")
    assert isinstance(result, ErrorResponse)
    assert "512" in result.error
    assert "EMBEDDER_DIM" in result.error
    mock_client.add_episode.assert_not_called()


async def test_ensure_embedder_dim_passes_when_matching(engine, mock_client) -> None:
    engine._embedder_checked = False  # type: ignore[attr-defined]
    mock_client.embedder.create = AsyncMock(return_value=[0.0] * 1536)
    await engine.ensure_embedder_dim()
    assert engine._embedder_checked is True


async def test_add_triplet_uses_resolved_group_id(engine, mock_client) -> None:
    await episodes.add_triplet(
        engine, source_name="A", edge_name="R", target_name="B", fact="f"
    )
    source_node, edge, target_node = mock_client.add_triplet.await_args.args
    assert source_node.group_id == "main"
    assert target_node.group_id == "main"
    assert edge.group_id == "main"


async def test_add_triplet_explicit_group_id_overrides(engine, mock_client) -> None:
    await episodes.add_triplet(
        engine, source_name="A", edge_name="R", target_name="B", fact="f", group_id="proj"
    )
    source_node, edge, target_node = mock_client.add_triplet.await_args.args
    assert source_node.group_id == "proj"
    assert edge.group_id == "proj"


async def test_add_memory_invalid_source_rejected_without_calling_engine(engine, mock_client) -> None:
    result = await episodes.add_memory(
        engine, name="n", episode_body="b", source="not-a-type"
    )
    assert isinstance(result, ErrorResponse)
    mock_client.add_episode.assert_not_called()


async def test_add_memory_invalid_reference_time_rejected(engine, mock_client) -> None:
    result = await episodes.add_memory(
        engine, name="n", episode_body="b", reference_time="not-a-date"
    )
    assert isinstance(result, ErrorResponse)
    assert "ISO-8601" in result.error
    mock_client.add_episode.assert_not_called()


@pytest.mark.parametrize("source", ["message", "text", "json"])
async def test_add_memory_accepts_valid_sources(engine, mock_client, source) -> None:
    mock_client.add_episode.return_value = Mock(episode=Mock(uuid="ep-1"))
    result = await episodes.add_memory(
        engine, name="n", episode_body="{}", source=source
    )
    assert isinstance(result, SuccessResponse)


async def test_add_triplet_success(engine, mock_client) -> None:
    result = await episodes.add_triplet(
        engine, source_name="Alice", edge_name="KNOWS", target_name="Bob", fact="Alice knows Bob"
    )
    assert isinstance(result, SuccessResponse)
    mock_client.add_triplet.assert_awaited_once()


async def test_add_triplet_propagates_failure(engine, mock_client) -> None:
    mock_client.add_triplet.side_effect = ValueError("embed failed")
    result = await episodes.add_triplet(
        engine, source_name="A", edge_name="R", target_name="B", fact="f"
    )
    assert isinstance(result, ErrorResponse)
    assert "embed failed" in result.error


async def test_add_memory_error_redacts_secrets(engine, mock_client) -> None:
    # An upstream client exception that embeds an API key must NOT reach the
    # caller verbatim — the secret is redacted from the error response.
    mock_client.add_episode.side_effect = RuntimeError(
        "401 Unauthorized: api_key=sk-secret123456789 rejected"
    )
    result = await episodes.add_memory(engine, name="n", episode_body="b")
    assert isinstance(result, ErrorResponse)
    assert "sk-secret123456789" not in result.error
    assert "[REDACTED]" in result.error
