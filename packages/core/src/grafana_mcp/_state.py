"""Global server state — settings and client pool.

Both are set exactly once at startup (CLI ``serve`` command) via ``init()``.
Tool functions retrieve them via ``get_settings()`` / ``get_pool()``.

Keeping state here (rather than in ``server.py``) breaks the otherwise-circular
import between ``server.py`` (which imports tools to register them) and the tool
modules (which need ``get_pool``/``get_settings``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client.pool import ClientPool
    from .settings import Settings

_settings: Settings | None = None
_pool: ClientPool | None = None


def init(settings: Settings, pool: ClientPool) -> None:
    """Initialize global state.  Call once before starting the server."""
    global _settings, _pool
    _settings = settings
    _pool = pool


def get_settings() -> Settings:
    """Return the active ``Settings`` instance.

    Raises:
        RuntimeError: If ``init()`` has not been called yet.
    """
    if _settings is None:
        raise RuntimeError(
            "Bifröst server not initialized — call _state.init() before serving."
        )
    return _settings


def get_pool() -> ClientPool:
    """Return the active ``ClientPool``.

    Raises:
        RuntimeError: If ``init()`` has not been called yet.
    """
    if _pool is None:
        raise RuntimeError(
            "Bifröst server not initialized — call _state.init() before serving."
        )
    return _pool
