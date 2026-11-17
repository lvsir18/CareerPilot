"""Connector registry (only implemented connectors are registered)."""

from __future__ import annotations

from app.connectors.alibaba import AlibabaTopConnector
from app.connectors.baidu import BaiduPublicConnector
from app.connectors.base import JobConnector
from app.connectors.errors import ConnectorNotConfigured
from app.connectors.fixture import FixtureConnector
from app.connectors.manual import ManualImportConnector
from app.core.config import Settings


def build_connector(source_type: str, settings: Settings) -> JobConnector:
    if source_type == "fixture":
        return FixtureConnector(settings)
    if source_type == "manual":
        return ManualImportConnector(settings)
    if source_type == "alibaba_openapi":
        return AlibabaTopConnector(settings)
    if source_type == "baidu_public":
        return BaiduPublicConnector(settings)
    raise ConnectorNotConfigured(f"未实现的数据源类型: {source_type}")


def implemented_source_types() -> tuple[str, ...]:
    return ("fixture", "manual", "alibaba_openapi", "baidu_public")
