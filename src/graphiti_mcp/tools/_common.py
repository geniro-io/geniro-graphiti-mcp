"""Shared helpers for the tool modules.

The namespace-resolution rule (an explicit ``group_id`` wins, else the engine's
configured default workspace) is the single most important cross-cutting
invariant — which namespace a write lands in — so it lives here once rather than
copy-pasted into every tool module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..engine import GraphitiEngine


def resolve_group_id(engine: GraphitiEngine, group_id: str | None) -> str:
    """The explicit ``group_id``, or the engine's configured default workspace."""
    return group_id or engine.settings.default_group_id


def resolve_group_ids(engine: GraphitiEngine, group_id: str | None) -> list[str]:
    """Single-element ``group_ids`` list for graphiti's plural search/retrieve APIs."""
    return [resolve_group_id(engine, group_id)]
