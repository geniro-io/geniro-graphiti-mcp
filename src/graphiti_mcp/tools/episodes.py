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
from graphiti_core.utils.bulk_utils import RawEpisode

from ..engine import GraphitiEngine
from ..errors import safe_error
from ..models import BulkAddResponse, EpisodeInput, ErrorResponse, SuccessResponse
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


def _to_raw_episode(ep: EpisodeInput) -> RawEpisode | str:
    """Convert an :class:`EpisodeInput` to a graphiti ``RawEpisode``.

    Returns the ``RawEpisode`` on success, or an error string describing the
    first problem (invalid source / non-ISO reference_time).
    """
    episode_type = _EPISODE_TYPES.get(ep.source.lower())
    if episode_type is None:
        return f"episode {ep.name!r}: invalid source {ep.source!r}"

    if ep.reference_time is None:
        ref_time = datetime.now(timezone.utc)
    else:
        try:
            ref_time = datetime.fromisoformat(ep.reference_time)
        except ValueError:
            return f"episode {ep.name!r}: reference_time {ep.reference_time!r} is not valid ISO-8601"
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)

    return RawEpisode(
        name=ep.name,
        content=ep.episode_body,
        source=episode_type,
        source_description=ep.source_description,
        reference_time=ref_time,
        uuid=ep.uuid,
    )


async def add_memory_bulk(
    engine: GraphitiEngine,
    episodes: list[EpisodeInput],
    *,
    group_id: str | None = None,
) -> BulkAddResponse | ErrorResponse:
    """Ingest many episodes in one batched, AWAITED operation.

    Faster than calling :func:`add_memory` N times — graphiti extracts, embeds
    and deduplicates the whole batch together (with the same edge-invalidation as
    the single path). Still synchronous: a failure becomes an
    :class:`ErrorResponse`, never a silent drop. The batch is validated up front,
    so one bad item rejects the call before any write.

    Args:
        episodes: The episodes to ingest. Keep batches modest (chunk very large
            loads) to stay within provider rate limits.
        group_id: Memory namespace; defaults to the configured workspace.
    """
    if not episodes:
        return ErrorResponse(error="No episodes provided for bulk add.")

    raw_episodes: list[RawEpisode] = []
    for ep in episodes:
        converted = _to_raw_episode(ep)
        if isinstance(converted, str):
            return ErrorResponse(error=f"Invalid bulk episode — {converted}.")
        raw_episodes.append(converted)

    gid = resolve_group_id(engine, group_id)
    try:
        await engine.ensure_embedder_dim()
        result = await engine.client.add_episode_bulk(raw_episodes, group_id=gid)
    except Exception as exc:  # noqa: BLE001 - surface every failure to the caller
        logger.exception("add_memory_bulk failed for %d episodes", len(raw_episodes))
        return ErrorResponse(error=f"Failed to add memories in bulk: {safe_error(exc)}")

    return BulkAddResponse(
        episodes_added=len(getattr(result, "episodes", []) or []),
        nodes_created=len(getattr(result, "nodes", []) or []),
        edges_created=len(getattr(result, "edges", []) or []),
        message=f"Added {len(raw_episodes)} episodes in bulk to group {gid!r}.",
    )
