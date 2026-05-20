"""API schemas for human review workflows."""

from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field


ReviewStatus = Literal["pending_review", "approved", "rejected"]


class PendingReviewRecord(BaseModel):
    review_id: str = Field(description="待人工复核记录 ID。")
    source_type: str = Field(description="来源类型。")
    status: ReviewStatus = Field(description="当前审批状态。")
    payload: Dict[str, Any] = Field(description="供人工复核使用的摘要信息。")
    created_at: str = Field(description="创建时间。")
    updated_at: str = Field(description="更新时间。")


class PendingReviewListResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "reviews": [
                    {
                        "review_id": "review-123",
                        "source_type": "contract_review",
                        "status": "pending_review",
                        "payload": {
                            "risk_level": "high",
                            "summary": "高风险劳动合同审查结果待人工复核",
                        },
                        "created_at": "2026-05-17T10:05:00+08:00",
                        "updated_at": "2026-05-17T10:05:00+08:00",
                    }
                ]
            }
        }
    )

    reviews: List[PendingReviewRecord] = Field(description="待人工复核记录列表。")


class ReviewDecisionResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "review_id": "review-123",
                "status": "approved",
                "final_answer": {"risk_level": "high", "disclaimer": "仅供参考，需人工复核"},
                "message": "审批通过，返回最终答案。",
            }
        }
    )

    review_id: str = Field(description="待人工复核记录 ID。")
    status: ReviewStatus = Field(description="审批后的状态。")
    final_answer: Dict[str, Any] | None = Field(
        default=None,
        description="审批通过后返回的完整审查结果；拒绝时为 null。",
    )
    message: str = Field(description="本次审批动作的说明信息。")
