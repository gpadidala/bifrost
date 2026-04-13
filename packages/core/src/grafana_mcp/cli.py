"""CLI entry points for the ``grafana-mcp`` command.

Commands::

    grafana-mcp serve             # boot the MCP server
    grafana-mcp validate-config   # dry-run config check
    grafana-mcp list-tools        # print the registered tool catalog
    grafana-mcp health            # ping every configured env
    grafana-mcp --version         # print version and exit
"""

from __future__ import annotations

import asyncio
import sys
from typing import Optional

import click

_VERSION = "1.3.0"


@click.group()
@click.version_option(version=_VERSION, prog_name="grafana-mcp")
def app() -> None:
    """Bifröst — multi-transport MCP server for Grafana."""


# ── serve ────────────────────────────────────────────────────────────────────


@app.command()
@click.option(
    "--transport",
    type=click.Choice(["sse", "http", "stdio"]),
    default=None,
    help="MCP transport (overrides GRAFANA_MCP_TRANSPORT__MODE).",
)
@click.option("--host", default=None, help="Bind host (overrides env).")
@click.option("--port", default=None, type=int, help="Listen port (overrides env).")
@click.option("--env", "environment", default=None, help="Active Grafana environment (dev|perf|prod).")
@click.option("--role", default=None, help="Active role (viewer|editor|admin).")
@click.option("--log-level", default=None, help="Log level (DEBUG|INFO|WARNING|ERROR).")
@click.option(
    "--log-format",
    type=click.Choice(["console", "json"]),
    default=None,
    help="Log format (console|json).",
)
def serve(
    transport: Optional[str],
    host: Optional[str],
    port: Optional[int],
    environment: Optional[str],
    role: Optional[str],
    log_level: Optional[str],
    log_format: Optional[str],
) -> None:
    """Boot the Bifröst MCP server."""
    from .client.pool import ClientPool
    from .logging import configure_logging
    from .settings import Settings
    from . import _state, server

    settings = Settings()

    # CLI flags override env-var settings
    if environment:
        settings.active_environment = environment  # type: ignore[assignment]
    if role:
        settings.active_role = role  # type: ignore[assignment]
    if transport:
        settings.transport.mode = transport  # type: ignore[assignment]
    if host:
        settings.transport.host = host
    if port:
        settings.transport.port = port
    if log_level:
        settings.log_level = log_level.upper()
    if log_format:
        settings.log_format = log_format  # type: ignore[assignment]

    configure_logging(level=settings.log_level, fmt=settings.log_format)

    pool = ClientPool(settings)
    _state.init(settings, pool)

    click.echo(
        f"→ Bifröst {_VERSION}  env={settings.active_environment}  "
        f"role={settings.active_role}  transport={settings.transport.mode}"
    )

    try:
        mode = settings.transport.mode
        if mode == "sse":
            server.run_sse(
                host=settings.transport.host,
                port=settings.transport.port,
                path_prefix=settings.transport.path_prefix,
                log_level=settings.log_level.lower(),
            )
        elif mode == "stdio":
            server.run_stdio()
        else:
            click.echo(f"Transport '{mode}' not yet supported — use sse or stdio.", err=True)
            sys.exit(1)
    finally:
        asyncio.run(pool.close_all())


# ── validate-config ──────────────────────────────────────────────────────────


@app.command("validate-config")
def validate_config() -> None:
    """Validate .env configuration without booting the server."""
    from .settings import Settings

    try:
        settings = Settings()
    except Exception as exc:  # noqa: BLE001
        click.echo(f"✗ Configuration invalid: {exc}", err=True)
        sys.exit(1)

    click.echo("✓ Configuration loaded successfully\n")
    click.echo(f"  active_environment : {settings.active_environment}")
    click.echo(f"  active_role        : {settings.active_role}")
    click.echo(f"  transport.mode     : {settings.transport.mode}")
    click.echo(f"  transport.host     : {settings.transport.host}")
    click.echo(f"  transport.port     : {settings.transport.port}")
    click.echo(f"  log_level          : {settings.log_level}")
    click.echo(f"  log_format         : {settings.log_format}")
    click.echo(f"\n  environments       : {list(settings.environments.keys())}")

    for env_name, env_cfg in settings.environments.items():
        has_viewer = env_cfg.service_accounts.has_token("viewer")
        has_editor = env_cfg.service_accounts.has_token("editor")
        has_admin = env_cfg.service_accounts.has_token("admin")
        tokens = f"viewer={'✓' if has_viewer else '✗'} editor={'✓' if has_editor else '✗'} admin={'✓' if has_admin else '✗'}"
        click.echo(f"  [{env_name}] {env_cfg.base_url}  {tokens}")


# ── list-tools ───────────────────────────────────────────────────────────────


@app.command("list-tools")
def list_tools() -> None:
    """Print all registered MCP tools with their minimum role."""
    from .rbac import TOOL_MINIMUM_ROLE

    # Import tools to ensure they are registered
    from . import tools as _tools  # noqa: F401

    click.echo(f"\n{'Tool':<30} {'Min Role':<12} Notes")
    click.echo("─" * 65)
    for tool_name, min_role in sorted(TOOL_MINIMUM_ROLE.items()):
        badge = {"viewer": "●", "editor": "◑", "admin": "○"}.get(min_role, "?")
        click.echo(f"  {tool_name:<28} {min_role:<12} {badge}")
    click.echo()


# ── health ────────────────────────────────────────────────────────────────────


@app.command()
def health() -> None:
    """Ping every configured Grafana environment and print a status table."""
    from .client.grafana import GrafanaClient
    from .settings import Settings

    settings = Settings()
    exit_code = 0

    click.echo(f"\n{'Env':<8} {'Role':<8} {'Status':<10} {'Latency':>8}")
    click.echo("─" * 40)

    for env_name, env_cfg in settings.environments.items():
        for role in ("viewer", "editor", "admin"):
            if not env_cfg.service_accounts.has_token(role):  # type: ignore[arg-type]
                click.echo(f"  {env_name:<6} {role:<8} {'(no token)':<10}")
                continue
            try:
                import time

                async def _check(env_cfg: object = env_cfg, role: str = role) -> tuple[bool, int]:
                    from .settings import EnvironmentConfig as EC

                    client = GrafanaClient(env_cfg, role)  # type: ignore[arg-type]
                    t0 = time.monotonic()
                    await client.get_health()
                    elapsed = int((time.monotonic() - t0) * 1000)
                    await client.close()
                    return True, elapsed

                ok, ms = asyncio.run(_check())
                click.echo(f"  {env_name:<6} {role:<8} {'✓ ok':<10} {ms:>5} ms")
            except Exception as exc:  # noqa: BLE001
                click.echo(f"  {env_name:<6} {role:<8} {'✗ ' + str(exc)[:30]:<10}")
                exit_code = 1

    click.echo()
    sys.exit(exit_code)
