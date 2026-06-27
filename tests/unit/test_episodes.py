"""The core guarantee: a failed write returns an error synchronously.

These tests encode the entire reason this rewrite exists — there is no queue, so
``add_memory`` cannot return success while the write fails in the background.
"""

from __future__ import annotations

from unittest.mock import Mock

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
