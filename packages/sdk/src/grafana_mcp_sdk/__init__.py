"""Bifröst SDK — high-level async Python client for Grafana.

Quick start::

    from grafana_mcp_sdk import BifrostClient

    async with BifrostClient.from_env() as client:
        health = await client.get_health()
        print(health)  # {"database": "ok", "version": "11.4.0"}
"""

from .client import BifrostClient

__version__ = "1.3.0"
__all__ = ["BifrostClient", "__version__"]
