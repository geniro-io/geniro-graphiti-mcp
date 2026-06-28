"""Search tools: ``search_nodes`` and ``search_memory_facts``.

- ``search_memory_facts`` uses the high-level ``graphiti.search`` which returns
  relationship edges (each carries a ``.fact``).
- ``search_nodes`` uses ``graphiti.search_`` with the node-hybrid RRF recipe,
  which returns entity nodes. RRF reranking needs no cross-encoder/LLM call.
"""

from __future__ import annotations

import logging

from graphiti_core.search.search_config_recipes import NODE_HYBRID_SEARCH_RRF

from ..engine import GraphitiEngine
from ..errors import safe_error
from ..models import (
    ErrorResponse,
    FactSearchResponse,
    NodeSearchResponse,
    format_fact,
    format_node,
)

logger = logging.getLogger(__name__)


def _resolve_group_ids(engine: GraphitiEngine, group_id: str | None) -> list[str]:
    return [group_id or engine.settings.default_group_id]


async def search_memory_facts(
    engine: GraphitiEngine,
    query: str,
    *,
    max_facts: int = 10,
    group_id: str | None = None,
) -> FactSearchResponse | ErrorResponse:
    """Search relationships (facts) relevant to ``query``."""
    if max_facts <= 0:
        return ErrorResponse(error="max_facts must be a positive integer.")
    try:
        edges = await engine.client.search(
            query=query,
            group_ids=_resolve_group_ids(engine, group_id),
            num_results=max_facts,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("search_memory_facts failed for query %r", query)
        return ErrorResponse(error=f"Fact search failed: {safe_error(exc)}")

    return FactSearchResponse(facts=[format_fact(e) for e in edges])


async def search_nodes(
    engine: GraphitiEngine,
    query: str,
    *,
    max_nodes: int = 10,
    group_id: str | None = None,
) -> NodeSearchResponse | ErrorResponse:
    """Search entity nodes relevant to ``query`` (node-hybrid RRF)."""
    if max_nodes <= 0:
        return ErrorResponse(error="max_nodes must be a positive integer.")

    config = NODE_HYBRID_SEARCH_RRF.model_copy(deep=True)
    config.limit = max_nodes

    try:
        results = await engine.client.search_(
            query=query,
            config=config,
            group_ids=_resolve_group_ids(engine, group_id),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("search_nodes failed for query %r", query)
        return ErrorResponse(error=f"Node search failed: {safe_error(exc)}")

    return NodeSearchResponse(nodes=[format_node(n) for n in results.nodes])
