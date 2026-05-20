"""API schemas for the legal RAG assistant."""

from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HealthResponse(BaseModel):
    status: str = Field(default="ok", description="服务状态。正常时固定为 ok。")


class ChatRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"query": "试用期最长多久？"},
                {"query": "请审查这份劳动合同：员工自愿放弃社保。"},
            ]
        }
    )

    query: str = Field(..., min_length=1, description="用户输入的问题或合同文本。")

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("query must not be blank")
        return cleaned


class ChatResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "answer": "合同审查完成，整体风险等级为 medium。建议重点复核：工资、社保。",
                "citations": ["《劳动合同法》第十七条：劳动合同应当具备劳动报酬、社会保险等条款。"],
                "route": "contract_review",
                "intent": "contract_review",
                "intent_source": "rule",
                "intent_confidence": 1.0,
                "tools_used": ["contract_review_rules"],
                "tool_trace": [
                    {
                        "name": "contract_review_rules",
                        "status": "ok",
                        "latency": 0.245,
                        "result_type": "contract_review",
                    }
                ],
                "result_type": "contract_review",
                "risk_level": "medium",
                "review_status": "not_required",
                "review_id": None,
                "contract_review": {"risk_level": "medium", "findings": []},
                "latency": 0.245,
            }
        }
    )

    answer: str = Field(description="最终返回给用户的回答。")
    citations: List[str] = Field(description="用于支撑回答的引用或证据片段。")
    route: str = Field(description="实际命中的业务路由。")
    intent: str = Field(description="识别出的意图类型。")
    intent_source: str = Field(default="", description="意图识别来源，例如 rule 或 llm。")
    intent_confidence: float = Field(default=0.0, ge=0, description="意图识别置信度。")
    tools_used: List[str] = Field(description="本次请求实际调用的工具列表。")
    tool_trace: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="本次请求的工具调用轨迹摘要，用于调试和验收。",
    )
    result_type: (
        Literal["law_qa", "policy_qa", "contract_review", "refusal", "compliance_qa"]
        | str
    ) = Field(
        default="",
        description="结果类型，通常与 route 对应。",
    )
    risk_level: Literal["low", "medium", "high"] | None = Field(
        default=None,
        description="合同审查场景下的整体风险等级。",
    )
    review_status: Literal["not_required", "pending_review"] | None = Field(
        default=None,
        description="合同审查是否需要人工复核。",
    )
    review_id: str | None = Field(default=None, description="人工复核记录 ID。")
    contract_review: Dict[str, Any] | None = Field(
        default=None,
        description="合同审查的结构化结果，仅在合同审查场景返回。",
    )
    latency: float = Field(..., ge=0, description="本次请求处理耗时，单位为秒。")


class ErrorResponse(BaseModel):
    error: str = Field(description="错误类型。")
    detail: str = Field(description="错误详情。")
