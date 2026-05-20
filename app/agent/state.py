"""State model for the LangGraph assistant workflow."""

from __future__ import annotations

from typing import Any, Dict, List, TypedDict


class AgentState(TypedDict, total=False):
    query: str
    intent: str
    intent_source: str
    intent_confidence: float
    planner_source: str
    allowed_tools: List[str]
    forced_tool: str | None
    tool_calls: List[Dict[str, Any]]
    tool_results: List[Dict[str, Any]]
    tool_trace: List[Dict[str, Any]]
    route: str
    result_type: str
    answer: str
    citations: List[str]
    tools_used: List[str]
    retrieved_contexts: List[str]
    retrieval_payload: Dict[str, Any]
    risk_level: str
    review_status: str
    review_id: str | None
    contract_review: Dict[str, Any] | None
