"""Administrative tools: ``build_communities``, ``summarize_saga``,
``clear_graph`` and ``get_status``."""

from __future__ import annotations

import logging

from graphiti_core.utils.maintenance.graph_data_operations import clear_data

from ..engine import GraphitiEngine
from ..errors import safe_error
from ..models import ErrorResponse, StatusResponse, SuccessResponse

logger = logging.getLogger(__name__)


def _resolve_group_id(engine: GraphitiEngine, group_id: str | None) -> str:
    return group_id or engine.settings.default_group_id


async def build_communities(
    engine: GraphitiEngine,
    *,
    group_id: str | None = None,
) -> SuccessResponse | ErrorResponse:
    """(Re)build community clusters for a group."""
    try:
        communities, _edges = await engine.client.build_communities(
            group_ids=[_resolve_group_id(engine, group_id)]
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("build_communities failed")
        return ErrorResponse(error=f"Failed to build communities: {safe_error(exc)}")

    return SuccessResponse(message=f"Built {len(communities)} communities.")


async def summarize_saga(
    engine: GraphitiEngine,
    saga_id: str,
) -> SuccessResponse | ErrorResponse:
    """Summarize a saga (a thread of related episodes)."""
    try:
        saga = await engine.client.summarize_saga(saga_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("summarize_saga failed for %s", saga_id)
        return ErrorResponse(error=f"Failed to summarize saga {saga_id!r}: {safe_error(exc)}")

    summary = getattr(saga, "summary", "") or "(no summary produced)"
    return SuccessResponse(message=summary)


async def clear_graph(
    engine: GraphitiEngine,
    *,
    group_id: str | None = None,
) -> SuccessResponse | ErrorResponse:
    """DESTRUCTIVE: delete all graph data for a single group, then rebuild indices.

    Scoped to ``group_id`` (defaults to the server's group) so it never wipes
    other namespaces, and only runs when explicitly invoked.
    """
    gid = _resolve_group_id(engine, group_id)
    try:
        await clear_data(engine.driver, group_ids=[gid])
        # clear_data drops data, not schema; rebuild indices to be safe.
        await engine.client.build_indices_and_constraints()
    except Exception as exc:  # noqa: BLE001
        logger.exception("clear_graph failed for group %s", gid)
        return ErrorResponse(error=f"Failed to clear graph for group {gid!r}: {safe_error(exc)}")

    return SuccessResponse(message=f"Cleared all graph data for group {gid!r}.")


async def get_status(engine: GraphitiEngine) -> StatusResponse:
    """Report Neo4j connectivity and the resolved providers.

    Unlike upstream there is no queue, so this reports the health that actually
    matters: can we reach Neo4j, and which models are wired in.
    """
    s = engine.settings
    connected = await engine.check_neo4j()
    return StatusResponse(
        status="ok" if connected else "degraded",
        neo4j_connected=connected,
        neo4j_uri=s.neo4j_uri,
        llm_provider=s.llm_provider.value,
        llm_model=s.llm_model,
        embedder_provider=s.embedder_provider.value,
        embedder_model=s.embedder_model,
        embedder_dim=s.embedder_dim,
        workspace=s.default_group_id,
        group_id=s.default_group_id,
        message=(
            "Neo4j reachable; providers resolved."
            if connected
            else "Neo4j is NOT reachable — check NEO4J_URI/credentials."
        ),
    )
