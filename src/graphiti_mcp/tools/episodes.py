"""Ingestion tools: ``add_memory`` and ``add_triplet``.

This is where the rewrite earns its keep. Upstream enqueues the episode and
returns an immediate "queued" success; a processing failure is only logged, so
the caller sees success while the graph stays empty (the silent-drop bug). Here
``add_memory`` AWAITS ``graphiti.add_episode`` and returns the real outcome: a
failure becomes an :class:`ErrorResponse` in the same call, never a false success.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from graphiti_core.edges import EntityEdge
from graphiti_core.nodes import EntityNode, EpisodeType

from ..engine import GraphitiEngine
from ..errors import safe_error
from ..models import ErrorResponse, SuccessResponse
from ._common import resolve_group_id

logger = logging.getLogger(__name__)

_EPISODE_TYPES = {
    "message": EpisodeType.message,
    "text": EpisodeType.text,
    "json": EpisodeType.json,
}


async def add_memory(
    engine: GraphitiEngine,
    name: str,
    episode_body: str,
    *,
    source: str = "message",
    source_description: str = "",
    group_id: str | None = None,
    reference_time: str | None = None,
    uuid: str | None = None,
) -> SuccessResponse | ErrorResponse:
    """Ingest an episode and AWAIT its processing.

    Args:
        name: Short human label for the episode.
        episode_body: The content. For ``source="json"`` this is a JSON string.
        source: One of ``message`` | ``text`` | ``json``.
        source_description: Provenance note (e.g. "user chat", "api payload").
        group_id: Memory namespace (workspace) to write into; defaults to the
            server's configured workspace (``GRAPHITI_WORKSPACE``).
        reference_time: ISO-8601 timestamp for the episode; defaults to now (UTC).
        uuid: Optional explicit episode UUID (for idempotent re-ingest).

    Returns:
        :class:`SuccessResponse` with the episode UUID, or :class:`ErrorResponse`
        if extraction/persistence failed — synchronously, never dropped.
    """
    episode_type = _EPISODE_TYPES.get(source.lower())
    if episode_type is None:
        return ErrorResponse(
            error=f"Invalid source {source!r}; expected one of {sorted(_EPISODE_TYPES)}."
        )

    if reference_time is None:
        ref_time = datetime.now(timezone.utc)
    else:
        try:
            ref_time = datetime.fromisoformat(reference_time)
        except ValueError:
            return ErrorResponse(
                error=f"reference_time {reference_time!r} is not valid ISO-8601."
            )
        # A bare ISO string ("2024-01-01T00:00:00") parses to a naive datetime;
        # normalize to aware UTC so it can't collide with the tz-aware default
        # (and graphiti's tz-aware temporal comparisons).
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)

    try:
        await engine.ensure_embedder_dim()
        result = await engine.client.add_episode(
            name=name,
            episode_body=episode_body,
            source_description=source_description,
            reference_time=ref_time,
            source=episode_type,
            group_id=resolve_group_id(engine, group_id),
            uuid=uuid,
        )
    except Exception as exc:  # noqa: BLE001 - surface every failure to the caller
        logger.exception("add_memory failed for episode %r", name)
        return ErrorResponse(error=f"Failed to add memory: {safe_error(exc)}")

    episode_uuid = getattr(getattr(result, "episode", None), "uuid", None)
    return SuccessResponse(
        message=f"Added memory {name!r}"
        + (f" (episode {episode_uuid})" if episode_uuid else "")
    )


async def add_triplet(
    engine: GraphitiEngine,
    source_name: str,
    edge_name: str,
    target_name: str,
    fact: str,
    *,
    group_id: str | None = None,
) -> SuccessResponse | ErrorResponse:
    """Add an explicit ``(source) -[edge]-> (target)`` fact triplet.

    Builds the two entity nodes and the relationship edge, then awaits
    ``graphiti.add_triplet`` (which embeds and persists them).
    """
    gid = resolve_group_id(engine, group_id)
    now = datetime.now(timezone.utc)

    try:
        await engine.ensure_embedder_dim()
        source_node = EntityNode(name=source_name, group_id=gid, labels=["Entity"])
        target_node = EntityNode(name=target_name, group_id=gid, labels=["Entity"])
        edge = EntityEdge(
            source_node_uuid=source_node.uuid,
            target_node_uuid=target_node.uuid,
            name=edge_name,
            fact=fact,
            group_id=gid,
            created_at=now,
        )
        await engine.client.add_triplet(source_node, edge, target_node)
    except Exception as exc:  # noqa: BLE001
        logger.exception("add_triplet failed: %s -[%s]-> %s", source_name, edge_name, target_name)
        return ErrorResponse(error=f"Failed to add triplet: {safe_error(exc)}")

    return SuccessResponse(
        message=f"Added triplet: {source_name} -[{edge_name}]-> {target_name}"
    )
