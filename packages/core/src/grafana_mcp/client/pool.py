"""``ClientPool`` — one ``GrafanaClient`` per (environment, role) pair.

The pool is created at server startup (in the CLI ``serve`` command), stored
in the global ``_state`` module, and torn down on server shutdown.  Tool
functions retrieve the client they need via ``pool.get(env_name, role)``.
"""

from __future__ import annotations

import structlog

from ..settings import GrafanaRole, Settings
from .grafana import GrafanaClient

logger = structlog.get_logger(__name__)


class ClientPool:
    """Lazy-initializing pool of ``GrafanaClient`` instances.

    Clients are created on first access and cached for the lifetime of the
    server process.  Call ``close_all()`` during shutdown to drain connections.

    Args:
        settings: The root ``Settings`` object — provides environment configs.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._clients: dict[tuple[str, str], GrafanaClient] = {}

    async def get(self, env_name: str, role: GrafanaRole) -> GrafanaClient:
        """Return (creating if needed) the client for *(env_name, role)*.

        Args:
            env_name: Environment key — ``"dev"``, ``"perf"``, or ``"prod"``.
            role:     Role string — ``"viewer"``, ``"editor"``, or ``"admin"``.

        Returns:
            A ready-to-use ``GrafanaClient`` for the given pair.

        Raises:
            ValueError: If *env_name* is not configured in ``settings.environments``.
        """
        key = (env_name.lower(), role)
        if key not in self._clients:
            env_config = self._settings.get_environment(env_name)
            client = GrafanaClient(env_config, role)
            self._clients[key] = client
            logger.debug(
                "client_pool_create",
                env=env_name,
                role=role,
                base_url=env_config.base_url,
            )
        return self._clients[key]

    async def close_all(self) -> None:
        """Close all pooled clients and release their HTTP connections."""
        for (env, role), client in self._clients.items():
            logger.debug("client_pool_close", env=env, role=role)
            await client.close()
        self._clients.clear()
