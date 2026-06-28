"""Geniro Graphiti MCP — a Graphiti memory server for the Claude CLI.

Embeds graphiti-core in-process and writes to Neo4j synchronously (awaited),
so ingestion errors propagate to the caller instead of being silently dropped
by a background queue.
"""

from __future__ import annotations

import os

# Privacy-first default for a local single-user tool: opt out of graphiti-core's
# anonymous usage telemetry unless the operator explicitly re-enables it. This
# MUST run before graphiti_core is imported (it reads the flag at import time),
# so it lives here in the package __init__ rather than in a submodule.
os.environ.setdefault("GRAPHITI_TELEMETRY_ENABLED", "false")

__version__ = "0.1.0"
