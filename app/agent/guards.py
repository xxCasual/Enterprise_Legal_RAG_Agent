"""Guardrail and rule-based routing helpers for the agent graph."""

from __future__ import annotations

from typing import Any, Dict, Sequence

from app.agent.constants import POLICY_ONLY_HINTS, PUBLIC_TOOL_NAMES, TOOL_BY_INTENT
from app.agent.intent_classifier import SUPPORTED_INTENTS, IntentClassifier
from app.agent.state import AgentState


intent_classifier = IntentClassifier()
rule_intent_classifier = IntentClassifier(enable_embedding_fallback=False)


def intent_router(state: AgentState) -> AgentState:
    query = state["query"]
    result = intent_classifier.classify(query)
    intent = result.intent
    if intent not in SUPPORTED_INTENTS:
        intent = "refusal"
    return {
        "intent": intent,
        "route": intent,
        "intent_source": result.source,
        "intent_confidence": round(result.confidence, 4),
    }


def guardrail_node(state: AgentState) -> AgentState:
    query = state["query"]
    result = rule_intent_classifier.classify(query)

    if _looks_like_contract_text(query):
        return _forced_tool_state(
            intent="contract_review",
            source="rule",
            confidence=1.0,
            tool_name="contract_review_rules",
            args={"contract_text": query},
        )

    if _is_compliance_combo_query(query) and result.intent not in {
        "contract_review",
        "refusal",
    }:
        return {
            "intent": "compliance_qa",
            "route": "compliance_qa",
            "result_type": "compliance_qa",
            "intent_source": "rule",
            "intent_confidence": 1.0,
            "planner_source": "guardrail",
            "allowed_tools": ["search_company_policy", "search_law_articles"],
        }

    if result.intent == "contract_review":
        return _forced_tool_state(
            intent="contract_review",
            source=result.source,
            confidence=result.confidence,
            tool_name="contract_review_rules",
            args={"contract_text": query},
        )

    if result.intent == "refusal" and result.source in {"rule", "empty"}:
        return _forced_tool_state(
            intent="refusal",
            source=result.source,
            confidence=result.confidence,
            tool_name="refuse_out_of_scope",
            args={"query": query},
        )

    mapped_tool = TOOL_BY_INTENT.get(result.intent)
    allowed_tools = [mapped_tool] if mapped_tool else list(PUBLIC_TOOL_NAMES)
    return {
        "intent": result.intent if result.source != "low_confidence" else "",
        "route": result.intent if result.source != "low_confidence" else "",
        "intent_source": result.source,
        "intent_confidence": round(result.confidence, 4),
        "planner_source": "guardrail",
        "allowed_tools": allowed_tools,
    }


def route_after_guardrail(state: AgentState) -> str:
    return "tool_executor" if state.get("tool_calls") else "tool_planner"


def _forced_tool_state(
    *,
    intent: str,
    source: str,
    confidence: float,
    tool_name: str,
    args: Dict[str, Any],
) -> AgentState:
    return {
        "intent": intent,
        "route": intent,
        "result_type": intent,
        "intent_source": source,
        "intent_confidence": round(confidence, 4),
        "planner_source": "guardrail",
        "allowed_tools": [tool_name],
        "forced_tool": tool_name,
        "tool_calls": [{"name": tool_name, "args": args}],
    }


def _is_compliance_combo_query(query: str) -> bool:
    if _contains_any(query, POLICY_ONLY_HINTS):
        return False

    has_law = _contains_any(
        query,
        (
            "法律",
            "法规",
            "法定",
            "劳动法",
            "劳动合同法",
            "仲裁",
            "经济补偿",
            "法律上",
            "法律规定",
        ),
    )
    has_policy = _contains_any(
        query,
        (
            "公司制度",
            "公司规定",
            "企业制度",
            "内部制度",
            "内部规定",
            "员工手册",
            "公司内部",
            "制度写",
            "制度都",
        ),
    )
    return has_law and has_policy


def _looks_like_contract_text(query: str) -> bool:
    clause_terms = (
        "合同期限",
        "试用期",
        "工资",
        "薪资",
        "标准工时",
        "工时",
        "社会保险",
        "社保",
        "解除劳动合同",
        "竞业限制",
        "甲方",
        "乙方",
    )
    hits = sum(1 for term in clause_terms if term in query)
    return hits >= 3 and _contains_any(query, ("合同", "甲方", "乙方"))


def _contains_any(query: str, keywords: Sequence[str]) -> bool:
    return any(keyword in query for keyword in keywords)
