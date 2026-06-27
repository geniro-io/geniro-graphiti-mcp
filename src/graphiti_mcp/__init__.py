"""Geniro Graphiti MCP — a Graphiti memory server for the Claude CLI.

Embeds graphiti-core in-process and writes to Neo4j synchronously (awaited),
so ingestion errors propagate to the caller instead of being silently dropped
by a background queue.
"""

__version__ = "0.1.0"
