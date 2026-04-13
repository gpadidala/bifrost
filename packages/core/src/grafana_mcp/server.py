"""ASGI application builder for Bifröst MCP server.

This module builds a Starlette application that wraps FastMCP's SSE or
streamable-HTTP transport and adds a ``/healthz`` endpoint for container
health probes.

All tool modules are imported here (as a side-effect) so that the
``@mcp.tool()`` decorators register their tools before the server starts.

Usage (via CLI)::

    from grafana_mcp import server
    server.run_sse(host="0.0.0.0", port=8765, path_prefix="/mcp")
"""

from __future__ import annotations

import anyio
import uvicorn
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from ._app import mcp

# Import all tool modules — this registers every @mcp.tool() decorator.
from . import tools as _tools  # noqa: F401
from . import ui_bridge

_tools  # suppress unused-import linters


def _build_starlette_app(path_prefix: str = "/mcp") -> Starlette:
    """Return a Starlette ASGI app with healthz + MCP SSE routes.

    Args:
        path_prefix: URL prefix for all MCP endpoints (default ``"/mcp"``).
                     SSE endpoint will be at ``{path_prefix}/sse``.
                     Message POST endpoint will be at ``{path_prefix}/messages/``.
    """
    prefix = path_prefix.rstrip("/")
    messages_path = f"{prefix}/messages/"

    sse_transport = SseServerTransport(messages_path)

    async def handle_sse(request: Request) -> None:
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send  # type: ignore[attr-defined]
        ) as streams:
            await mcp._mcp_server.run(  # type: ignore[attr-defined]
                streams[0],
                streams[1],
                mcp._mcp_server.create_initialization_options(),  # type: ignore[attr-defined]
            )

    async def healthz(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "version": "1.3.0"})

    return Starlette(
        routes=[
            Route("/healthz", healthz),
            Route(f"{prefix}/sse", handle_sse),
            Mount(messages_path, app=sse_transport.handle_post_message),
            *ui_bridge.routes(),
        ],
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                allow_methods=["GET", "POST", "OPTIONS"],
                allow_headers=["*"],
            ),
        ],
    )


def run_sse(
    host: str = "0.0.0.0",
    port: int = 8765,
    path_prefix: str = "/mcp",
    log_level: str = "info",
) -> None:
    """Start the MCP SSE server synchronously (blocks until stopped).

    Args:
        host:        Bind address (default ``"0.0.0.0"``).
        port:        Listen port (default ``8765``).
        path_prefix: URL prefix for MCP endpoints (default ``"/mcp"``).
        log_level:   Uvicorn log level string (default ``"info"``).
    """
    app = _build_starlette_app(path_prefix)
    uvicorn.run(app, host=host, port=port, log_level=log_level.lower())


def run_stdio() -> None:
    """Start the MCP server over stdio (for direct LLM tool use, e.g. in Claude Desktop).

    This transport reads from stdin and writes to stdout — do not mix with
    any other output on those streams.
    """
    import asyncio

    asyncio.run(_run_stdio_async())


async def _run_stdio_async() -> None:
    from mcp.server.stdio import stdio_server

    async with stdio_server() as streams:
        await mcp._mcp_server.run(  # type: ignore[attr-defined]
            streams[0],
            streams[1],
            mcp._mcp_server.create_initialization_options(),  # type: ignore[attr-defined]
        )
