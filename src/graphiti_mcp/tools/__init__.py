"""MCP tool implementations.

Each tool is a plain async function taking a :class:`~graphiti_mcp.engine.GraphitiEngine`
as its first argument and returning a pydantic response model. ``server.py``
registers thin FastMCP wrappers around them; keeping the engine explicit here
makes every tool unit-testable with a mocked Graphiti client.
"""
