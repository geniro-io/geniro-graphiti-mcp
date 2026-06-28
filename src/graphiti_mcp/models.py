"""Pydantic response models and formatting helpers.

These shape what the MCP tools return to the Claude CLI. Every mutating/admin
tool returns either a :class:`SuccessResponse` or an :class:`ErrorResponse`; the
distinction is the load-bearing contract behind the "no silent drop" guarantee —
a failed write returns an ``ErrorResponse`` synchronously, never a success.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SuccessResponse(BaseModel):
    """Returned by a tool whose side effect completed successfully."""

    status: str = "success"
    message: str


class ErrorResponse(BaseModel):
    """Returned by a tool whose operation failed.

    The error is surfaced in the same call that triggered the work — there is no
    background queue that could swallow it.
    """

    status: str = "error"
    error: str


class NodeResult(BaseModel):
    """A single entity node returned from a node search."""

    uuid: str
    name: str
    summary: str = ""
    labels: list[str] = Field(default_factory=list)
    group_id: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None


class FactResult(BaseModel):
    """A single relationship (edge) returned from a fact search."""

    uuid: str
    fact: str
    name: str = ""
    source_node_uuid: str = ""
    target_node_uuid: str = ""
    group_id: str = ""
    valid_at: str | None = None
    invalid_at: str | None = None
    created_at: str | None = None


class EpisodeResult(BaseModel):
    """A single episodic node (an ingested memory)."""

    uuid: str
    name: str
    content: str = ""
    source: str = ""
    source_description: str = ""
    group_id: str = ""
    created_at: str | None = None


class NodeSearchResponse(BaseModel):
    status: str = "success"
    nodes: list[NodeResult]


class FactSearchResponse(BaseModel):
    status: str = "success"
    facts: list[FactResult]


class EpisodeListResponse(BaseModel):
    status: str = "success"
    episodes: list[EpisodeResult]


class GroupIdListResponse(BaseModel):
    """The distinct group_ids (memory namespaces) present in the graph."""

    status: str = "success"
    group_ids: list[str]


class StatusResponse(BaseModel):
    """Health/diagnostics for :func:`get_status` — reports connectivity and the
    resolved providers, NOT queue depth (there is no queue)."""

    status: str
    neo4j_connected: bool
    neo4j_uri: str
    llm_provider: str
    llm_model: str
    embedder_provider: str
    embedder_model: str
    embedder_dim: int
    group_id: str
    message: str = ""


# ── Formatting helpers (graphiti-core objects → response models) ─────────


def _iso(value: Any) -> str | None:
    """Render a datetime-ish value as ISO-8601, tolerating ``None``."""
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    return isoformat() if callable(isoformat) else str(value)


def format_node(node: Any) -> NodeResult:
    return NodeResult(
        uuid=node.uuid,
        name=node.name,
        summary=getattr(node, "summary", "") or "",
        labels=list(getattr(node, "labels", []) or []),
        group_id=getattr(node, "group_id", "") or "",
        attributes=dict(getattr(node, "attributes", {}) or {}),
        created_at=_iso(getattr(node, "created_at", None)),
    )


def format_fact(edge: Any) -> FactResult:
    return FactResult(
        uuid=edge.uuid,
        fact=getattr(edge, "fact", "") or "",
        name=getattr(edge, "name", "") or "",
        source_node_uuid=getattr(edge, "source_node_uuid", "") or "",
        target_node_uuid=getattr(edge, "target_node_uuid", "") or "",
        group_id=getattr(edge, "group_id", "") or "",
        valid_at=_iso(getattr(edge, "valid_at", None)),
        invalid_at=_iso(getattr(edge, "invalid_at", None)),
        created_at=_iso(getattr(edge, "created_at", None)),
    )


def format_episode(node: Any) -> EpisodeResult:
    source = getattr(node, "source", "")
    # EpisodeType is an enum; render its value.
    source_str = getattr(source, "value", source) or ""
    return EpisodeResult(
        uuid=node.uuid,
        name=node.name,
        content=getattr(node, "content", "") or "",
        source=str(source_str),
        source_description=getattr(node, "source_description", "") or "",
        group_id=getattr(node, "group_id", "") or "",
        created_at=_iso(getattr(node, "created_at", None)),
    )
