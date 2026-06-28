"""Retrieval and deletion tools.

``get_episodes``, ``get_episode_entities``, ``get_entity_edge``,
``delete_entity_edge`` and ``delete_episode``. Lookups and deletes go through
graphiti-core's node/edge classmethods against the engine driver.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from graphiti_core.edges import EntityEdge
from graphiti_core.nodes import EpisodicNode

from ..engine import GraphitiEngine
from ..errors import safe_error
from ..models import (
    EpisodeListResponse,
    ErrorResponse,
    FactResult,
    NodeSearchResponse,
    SuccessResponse,
    format_episode,
    format_fact,
    format_node,
)

logger = logging.getLogger(__name__)


def _resolve_group_ids(engine: GraphitiEngine, group_id: str | None) -> list[str]:
    return [group_id or engine.settings.default_group_id]


async def get_episodes(
    engine: GraphitiEngine,
    *,
    last_n: int = 10,
    group_id: str | None = None,
) -> EpisodeListResponse | ErrorResponse:
    """Return the most recent ``last_n`` episodes for a group."""
    if last_n <= 0:
        return ErrorResponse(error="last_n must be a positive integer.")
    try:
        episodes = await engine.client.retrieve_episodes(
            reference_time=datetime.now(timezone.utc),
            last_n=last_n,
            group_ids=_resolve_group_ids(engine, group_id),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("get_episodes failed")
        return ErrorResponse(error=f"Failed to get episodes: {safe_error(exc)}")

    return EpisodeListResponse(episodes=[format_episode(e) for e in episodes])


async def get_episode_entities(
    engine: GraphitiEngine,
    episode_uuid: str,
) -> NodeSearchResponse | ErrorResponse:
    """Return the entity nodes extracted from a given episode."""
    try:
        results = await engine.client.get_nodes_and_edges_by_episode([episode_uuid])
    except Exception as exc:  # noqa: BLE001
        logger.exception("get_episode_entities failed for %s", episode_uuid)
        return ErrorResponse(error=f"Failed to get episode entities: {safe_error(exc)}")

    return NodeSearchResponse(nodes=[format_node(n) for n in results.nodes])


async def get_entity_edge(
    engine: GraphitiEngine,
    uuid: str,
) -> FactResult | ErrorResponse:
    """Return a single relationship edge by UUID."""
    try:
        edge = await EntityEdge.get_by_uuid(engine.driver, uuid)
    except Exception as exc:  # noqa: BLE001
        logger.exception("get_entity_edge failed for %s", uuid)
        return ErrorResponse(error=f"Entity edge {uuid!r} not found: {safe_error(exc)}")

    return format_fact(edge)


async def delete_entity_edge(
    engine: GraphitiEngine,
    uuid: str,
) -> SuccessResponse | ErrorResponse:
    """Delete a relationship edge by UUID."""
    try:
        edge = await EntityEdge.get_by_uuid(engine.driver, uuid)
        await edge.delete(engine.driver)
    except Exception as exc:  # noqa: BLE001
        logger.exception("delete_entity_edge failed for %s", uuid)
        return ErrorResponse(error=f"Failed to delete entity edge {uuid!r}: {safe_error(exc)}")

    return SuccessResponse(message=f"Deleted entity edge {uuid}")


async def delete_episode(
    engine: GraphitiEngine,
    episode_uuid: str,
) -> SuccessResponse | ErrorResponse:
    """Delete an episode (and its derived graph data) by UUID."""
    try:
        # remove_episode unwinds the episode's contribution to the graph;
        # fall back to a direct node delete if the engine lacks it.
        remove = getattr(engine.client, "remove_episode", None)
        if remove is not None:
            await remove(episode_uuid)
        else:  # pragma: no cover - defensive for older graphiti-core
            await EpisodicNode.delete_by_uuids(engine.driver, [episode_uuid])
    except Exception as exc:  # noqa: BLE001
        logger.exception("delete_episode failed for %s", episode_uuid)
        return ErrorResponse(error=f"Failed to delete episode {episode_uuid!r}: {safe_error(exc)}")

    return SuccessResponse(message=f"Deleted episode {episode_uuid}")
