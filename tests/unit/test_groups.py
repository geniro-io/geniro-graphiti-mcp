"""list_group_ids tool."""

from __future__ import annotations

from unittest.mock import AsyncMock

from graphiti_mcp.models import ErrorResponse, GroupIdListResponse
from graphiti_mcp.tools import groups


async def test_list_group_ids_dedupes_and_sorts(engine, mock_client) -> None:
    # Nodes and relationships both contribute group_ids; duplicates collapse.
    records = [
        {"group_id": "main"},
        {"group_id": "project-x"},
        {"group_id": "main"},
        {"group_id": None},
    ]
    mock_client.driver.execute_query = AsyncMock(return_value=(records, None, None))

    result = await groups.list_group_ids(engine)

    assert isinstance(result, GroupIdListResponse)
    assert result.group_ids == ["main", "project-x"]


async def test_list_group_ids_empty(engine, mock_client) -> None:
    mock_client.driver.execute_query = AsyncMock(return_value=([], None, None))
    result = await groups.list_group_ids(engine)
    assert isinstance(result, GroupIdListResponse)
    assert result.group_ids == []


async def test_list_group_ids_propagates_failure(engine, mock_client) -> None:
    mock_client.driver.execute_query = AsyncMock(side_effect=RuntimeError("db down"))
    result = await groups.list_group_ids(engine)
    assert isinstance(result, ErrorResponse)
    assert "db down" in result.error
