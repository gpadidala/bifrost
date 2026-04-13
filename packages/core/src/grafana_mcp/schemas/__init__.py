"""Pydantic output schemas for all Bifröst MCP tools."""

from .alert import AlertInstance, AlertRule, Silence, SilenceResult
from .common import GrafanaHealth, ServerInfo
from .dashboard import DashboardDetail, DashboardPanel, DashboardSummary
from .datasource import DatasourceDetail, DatasourceSummary, QueryResult, TestResult
from .folder import Folder
from .user import ServiceAccount, UserSummary

__all__ = [
    "AlertInstance",
    "AlertRule",
    "Silence",
    "SilenceResult",
    "GrafanaHealth",
    "ServerInfo",
    "DashboardDetail",
    "DashboardPanel",
    "DashboardSummary",
    "DatasourceDetail",
    "DatasourceSummary",
    "QueryResult",
    "TestResult",
    "Folder",
    "ServiceAccount",
    "UserSummary",
]
