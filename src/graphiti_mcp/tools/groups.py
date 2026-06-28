"""Group (namespace) management tools.

``group_id`` partitions memories into namespaces (e.g. one per project). This is
a convenience for discovering which namespaces exist; deletion of a whole group
is already covered by ``clear_graph(group_id=...)``.
"""

from __future__ import annotations

import logging

from ..engine import GraphitiEngine
from ..errors import safe_error
from ..models import ErrorResponse, GroupIdListResponse

logger = logging.getLogger(__name__)

# Distinct group_ids across both nodes and relationships.
_LIST_GROUP_IDS_QUERY = (
    "MATCH (n) WHERE n.group_id IS NOT NULL "
    "RETURN DISTINCT n.group_id AS group_id "
    "UNION "
    "MATCH ()-[r]-() WHERE r.group_id IS NOT NULL "
    "RETURN DISTINCT r.group_id AS group_id"
)


async def list_group_ids(engine: GraphitiEngine) -> GroupIdListResponse | ErrorResponse:
    """Return the distinct group_ids (namespaces) present in the graph."""
    try:
        records, _summary, _keys = await engine.driver.execute_query(_LIST_GROUP_IDS_QUERY)
    except Exception as exc:  # noqa: BLE001
        logger.exception("list_group_ids failed")
        return ErrorResponse(error=f"Failed to list group IDs: {safe_error(exc)}")

    group_ids = sorted({r["group_id"] for r in records if r["group_id"]})
    return GroupIdListResponse(group_ids=group_ids)
