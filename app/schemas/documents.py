"""API schemas for uploaded company documents."""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field


class DocumentRecord(BaseModel):
    doc_id: str = Field(description="文档唯一标识。")
    file_name: str = Field(description="原始文件名。")
    source_type: str = Field(description="文档来源类型。")
    chunk_count: int = Field(..., ge=0, description="切分后的 chunk 数量。")
    created_at: str = Field(description="文档入库时间。")
    status: Literal["pending", "indexing", "ready", "failed"] = Field(
        default="ready",
        description="文档索引状态。",
    )
    error_message: str | None = Field(default=None, description="索引失败原因。")
    indexed_at: str | None = Field(default=None, description="索引完成时间。")
    task_id: str | None = Field(default=None, description="后台索引任务 ID。")


class DocumentUploadResponse(DocumentRecord):
    pass


class DocumentListResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "documents": [
                    {
                        "doc_id": "doc-1",
                        "file_name": "员工手册.pdf",
                        "source_type": "upload",
                        "chunk_count": 12,
                        "created_at": "2026-05-17T10:00:00+08:00",
                    }
                ]
            }
        }
    )

    documents: List[DocumentRecord] = Field(description="当前已入库的企业制度文档列表。")
