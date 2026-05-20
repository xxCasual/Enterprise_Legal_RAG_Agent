"""LangGraph workflow wiring for the enterprise legal assistant."""

from __future__ import annotations

import time
from typing import Any, Dict

from langgraph.graph import END, START, StateGraph

from app.agent.answering import answer_node, _state_from_payload
from app.agent.constants import (
    PLANNER_SYSTEM_PROMPT,
    POLICY_ONLY_HINTS,
    PUBLIC_TOOL_NAMES,
    TOOL_BY_INTENT,
)
from app.agent.executor import execute_tool_state
from app.agent.guards import (
    guardrail_node,
    intent_classifier,
    intent_router,
    route_after_guardrail,
    rule_intent_classifier,
    _contains_any,
    _forced_tool_state,
    _is_compliance_combo_query,
    _looks_like_contract_text,
)
from app.agent.planner import (
    build_tool_plan_state,
    plan_tools_with_llm,
    _coerce_tool_args,
    _fallback_tool_calls,
    _normalize_tool_calls,
    _tool_calls_from_message,
)
from app.agent.state import AgentState
from app.agent.tools import (
    refuse_out_of_scope,
    registered_agent_tools,
    review_labor_contract,
    search_company_policy,
    search_law_articles,
)


def tool_planner_node(state: AgentState) -> AgentState:
    return build_tool_plan_state(state, plan_tools_with_llm)


def tool_executor_node(state: AgentState) -> AgentState:
    return execute_tool_state(state, _execute_tool)


def route_after_intent(state: AgentState) -> str:
    return {
        "law_qa": "law_qa_node",
        "policy_qa": "policy_qa_node",
        "contract_review": "contract_review_node",
        "refusal": "refusal_node",
    }.get(state.get("intent", "law_qa"), "law_qa_node")


def law_qa_node(state: AgentState) -> AgentState:
    payload = search_law_articles(state["query"])
    return _state_from_payload(payload, ["search_law_articles"], [])


def policy_qa_node(state: AgentState) -> AgentState:
    payload = search_company_policy(state["query"])
    return _state_from_payload(payload, ["search_company_policy"], [])


def contract_review_node(state: AgentState) -> AgentState:
    payload = review_labor_contract(state["query"])
    return _state_from_payload(payload, ["contract_review_rules"], [])


def refusal_node(state: AgentState) -> AgentState:
    payload = refuse_out_of_scope(state["query"])
    return _state_from_payload(payload, [], [])


def build_agent_graph():
    builder = StateGraph(AgentState)
    builder.add_node("guardrail", guardrail_node)
    builder.add_node("tool_planner", tool_planner_node)
    builder.add_node("tool_executor", tool_executor_node)
    builder.add_node("answer", answer_node)
    builder.add_edge(START, "guardrail")
    builder.add_conditional_edges(
        "guardrail",
        route_after_guardrail,
        {
            "tool_planner": "tool_planner",
            "tool_executor": "tool_executor",
        },
    )
    builder.add_edge("tool_planner", "tool_executor")
    builder.add_edge("tool_executor", "answer")
    builder.add_edge("answer", END)
    return builder.compile()


agent_graph = build_agent_graph()


def run_agent_chat(query: str) -> Dict[str, object]:
    started_at = time.perf_counter()
    result = agent_graph.invoke({"query": query})
    latency = round(time.perf_counter() - started_at, 3)
    return {
        "answer": result.get("answer", ""),
        "citations": result.get("citations", []),
        "route": result.get("route", result.get("intent", "")),
        "intent": result.get("intent", ""),
        "intent_source": result.get("intent_source", ""),
        "intent_confidence": result.get("intent_confidence", 0.0),
        "tools_used": result.get("tools_used", []),
        "tool_trace": result.get("tool_trace", []),
        "result_type": result.get("result_type", result.get("route", "")),
        "risk_level": result.get("risk_level"),
        "review_status": result.get("review_status"),
        "review_id": result.get("review_id"),
        "contract_review": result.get("contract_review"),
        "latency": latency,
    }


def _execute_tool(name: str, args: Dict[str, Any], query: str) -> Dict[str, Any]:
    if name == "search_law_articles":
        return search_law_articles(str(args.get("query") or query))
    if name == "search_company_policy":
        return search_company_policy(str(args.get("query") or query))
    if name == "contract_review_rules":
        return review_labor_contract(
            str(args.get("contract_text") or args.get("query") or query),
            include_evidence=False,
        )
    if name == "refuse_out_of_scope":
        return refuse_out_of_scope(str(args.get("query") or query))
    raise ValueError(f"Unknown tool: {name}")


__all__ = [
    "PLANNER_SYSTEM_PROMPT",
    "POLICY_ONLY_HINTS",
    "PUBLIC_TOOL_NAMES",
    "TOOL_BY_INTENT",
    "agent_graph",
    "answer_node",
    "build_agent_graph",
    "contract_review_node",
    "guardrail_node",
    "intent_classifier",
    "intent_router",
    "law_qa_node",
    "plan_tools_with_llm",
    "policy_qa_node",
    "refusal_node",
    "registered_agent_tools",
    "route_after_guardrail",
    "route_after_intent",
    "rule_intent_classifier",
    "run_agent_chat",
    "tool_executor_node",
    "tool_planner_node",
    "_coerce_tool_args",
    "_contains_any",
    "_execute_tool",
    "_fallback_tool_calls",
    "_forced_tool_state",
    "_is_compliance_combo_query",
    "_looks_like_contract_text",
    "_normalize_tool_calls",
    "_state_from_payload",
    "_tool_calls_from_message",
]
