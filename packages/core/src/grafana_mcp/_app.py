"""Central FastMCP application instance.

Imported by both ``server.py`` (to build the ASGI app) and every tool module
(to register tools via ``@mcp.tool()``).  Kept in its own module to avoid
circular imports — tools import ``_app.mcp`` and ``_state.get_pool()``;
``server.py`` imports ``_app.mcp`` and ``tools`` (to trigger registration).
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "Bifrost — Grafana MCP Server",
    instructions=(
        "You are connected to a Bifröst MCP server that provides typed tools "
        "for querying and managing Grafana. "
        "Three roles are available: viewer (read-only), editor (can silence alerts), "
        "admin (full management). "
        "Specify 'environment' and 'role' kwargs to target a non-default environment. "
        "Always confirm destructive actions (silences, etc.) with the user first."
    ),
)
