"""Tenacity retry policy for Grafana HTTP calls.

Only transient errors are retried:
  - Network-level errors (``httpx.RequestError``)
  - HTTP 429 Too Many Requests
  - HTTP 5xx server errors

Client errors (4xx except 429) are NOT retried — they represent programmer
or configuration mistakes that won't resolve themselves.
"""

from __future__ import annotations

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)


def _is_retryable(exc: BaseException) -> bool:
    """Return True for network errors, 429, and 5xx responses."""
    if isinstance(exc, httpx.RequestError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False


#: Standard retry decorator — apply to ``GrafanaClient`` request methods.
grafana_retry = retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=5.0),
    reraise=True,
)
