"""Tool registration — importing this package registers all tools with ``_app.mcp``."""

from . import alerts, dashboards, datasources, folders, users, utility

__all__ = ["alerts", "dashboards", "datasources", "folders", "users", "utility"]
