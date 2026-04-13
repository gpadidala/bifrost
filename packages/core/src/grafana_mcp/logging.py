"""Structured logging configuration for Bifröst.

Configure once at startup via ``configure_logging()``. All modules then
import ``structlog.get_logger()`` directly — no need to import this module
again after startup.

The ``redact_auth_headers`` processor strips sensitive values from log events
so that tokens never appear in log output (JSON or console).
"""

from __future__ import annotations

import logging
from typing import Any, Literal

import structlog


_SENSITIVE_KEY_PATTERNS = frozenset(
    ["token", "authorization", "api_key", "password", "secret", "bearer"]
)


def redact_auth_headers(
    logger: Any,  # noqa: ANN401 — structlog processor signature
    method: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Replace sensitive values in the structlog event dict with ``<redacted>``.

    Walks the entire top-level event dict and redacts any value whose key
    contains a known sensitive substring (case-insensitive).
    """
    for key in list(event_dict.keys()):
        lower_key = key.lower()
        if any(pat in lower_key for pat in _SENSITIVE_KEY_PATTERNS):
            event_dict[key] = "<redacted>"
    return event_dict


def configure_logging(
    level: str = "INFO",
    fmt: Literal["console", "json"] = "console",
) -> None:
    """Configure structlog and stdlib logging for Bifröst.

    Call this exactly once at application startup (in the CLI ``serve``
    command) before any log messages are emitted.

    Args:
        level: Logging level string — ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``.
        fmt:   Output format — ``console`` for human-readable dev output,
               ``json`` for machine-readable production output.
    """
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        redact_auth_headers,
        structlog.processors.StackInfoRenderer(),
    ]

    if fmt == "json":
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(level.upper())

    # Quiet noisy third-party loggers
    for noisy in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
