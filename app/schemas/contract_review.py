"""API schemas for labor contract risk review."""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


RiskLevel = Literal["low", "medium", "high"]
ClauseStatus = Literal["present", "missing", "unclear"]
ClauseType = Literal[
    "probation",
    "term",
    "salary",
    "working_hours",
    "social_insurance",
    "termination",
    "non_compete",
]


class ContractReviewRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "contract_text": (
                        "甲方可随时解除合同且不支付经济补偿。"
                        "乙方自愿放弃社保，由甲方按月发放补贴代替。"
                    )
                }
            ]
        }
    )

    contract_text: str = Field(..., min_length=1, description="待审查的劳动合同正文。")
    include_evidence: bool = Field(
        default=False,
        description="是否同步检索法律依据。默认关闭以优先返回规则审查结果。",
    )

    @field_validator("contract_text")
    @classmethod
    def contract_text_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("contract_text must not be blank")
        return cleaned


class ContractFinding(BaseModel):
    clause_type: ClauseType = Field(description="条款类型标识。")
    clause_name: str = Field(description="条款中文名称。")
    status: ClauseStatus = Field(description="条款识别状态：已出现、缺失或表述不清。")
    risk_level: RiskLevel = Field(description="该条款对应的风险等级。")
    extracted_text: str = Field(description="从合同中抽取到的相关原文片段。")
    analysis: str = Field(description="对该条款风险的简要分析。")
    evidence: List[str] = Field(description="用于支撑判断的法律依据片段。")
    suggestion: str = Field(description="建议的人审关注点或修改建议。")


class ContractReviewResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "risk_level": "high",
                "findings": [
                    {
                        "clause_type": "social_insurance",
                        "clause_name": "社保",
                        "status": "present",
                        "risk_level": "high",
                        "extracted_text": "乙方自愿放弃社保，由甲方按月发放补贴代替。",
                        "analysis": "条款疑似以补贴替代社保缴纳，属于高风险约定。",
                        "evidence": ["《劳动合同法》第十七条：劳动合同应当具备社会保险条款。"],
                        "suggestion": "建议删除放弃社保或补贴替代社保的表述，并明确依法缴纳社会保险。",
                    }
                ],
                "evidence": ["《劳动合同法》第十七条：劳动合同应当具备社会保险条款。"],
                "suggestions": ["建议删除放弃社保或补贴替代社保的表述，并明确依法缴纳社会保险。"],
                "disclaimer": "仅供参考，需人工复核",
                "latency": 0.312,
                "review_status": "pending_review",
                "review_id": "review-123",
            }
        }
    )

    risk_level: RiskLevel = Field(description="合同整体风险等级。")
    findings: List[ContractFinding] = Field(description="逐条款结构化审查结果。")
    evidence: List[str] = Field(description="汇总后的法律依据片段。")
    suggestions: List[str] = Field(description="汇总后的审查建议。")
    disclaimer: str = Field(description="免责声明。")
    latency: float = Field(..., ge=0, description="本次审查耗时，单位为秒。")
    review_status: Literal["not_required", "pending_review"] = Field(
        default="not_required",
        description="是否需要进入人工复核。",
    )
    review_id: str | None = Field(default=None, description="人工复核记录 ID。")
    evidence_status: Literal["not_requested", "complete"] = Field(
        default="not_requested",
        description="法律依据补全状态。",
    )
