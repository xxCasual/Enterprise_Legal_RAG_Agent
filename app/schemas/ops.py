"""Operational schemas for readiness and dependency status."""

from __future__ import annotations

from typing import Dict

from pydantic import BaseModel, Field


class DependencyStatus(BaseModel):
    status: str = Field(description="依赖状态，例如 ok、degraded、error 或 not_configured。")
    detail: str = Field(default="", description="依赖状态说明。")


class ReadyResponse(BaseModel):
    status: str = Field(description="整体就绪状态。")
    dependencies: Dict[str, DependencyStatus] = Field(description="关键依赖状态。")
    document_counts: Dict[str, int] = Field(
        default_factory=dict,
        description="制度文档按索引状态聚合的数量。",
    )
