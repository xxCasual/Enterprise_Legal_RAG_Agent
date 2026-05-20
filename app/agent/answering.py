"""Answer aggregation and state conversion helpers for the agent graph."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence

from app.agent.state import AgentState
from app.agent.tools import refuse_out_of_scope


def answer_node(state: AgentState) -> AgentState:
    tool_results = state.get("tool_results", [])
    tool_trace = state.get("tool_trace", [])
    tools_used = state.get("tools_used", [])
    successful = [result for result in tool_results if result.get("status") == "ok"]

    if not successful:
        payload = refuse_out_of_scope(state["query"])
        return _state_from_payload(
            payload,
            tools_used=["refuse_out_of_scope"],
            tool_trace=tool_trace
            or [
                {
                    "name": "refuse_out_of_scope",
                    "args": {"query": _truncate(state["query"])},
                    "status": "ok",
                    "latency": 0.0,
                    "route": "refusal",
                    "result_type": "refusal",
                }
            ],
            intent="refusal",
            intent_source=state.get("planner_source", "fallback"),
            intent_confidence=0.0,
        )

    if len(successful) == 1:
        payload = successful[0].get("payload", {})
        return _state_from_payload(
            payload,
            tools_used=tools_used or [successful[0]["name"]],
            tool_trace=tool_trace,
            intent=str(
                payload.get("result_type")
                or payload.get("route")
                or state.get("intent")
                or ""
            ),
            intent_source=state.get("planner_source", state.get("intent_source", "")),
            intent_confidence=float(state.get("intent_confidence") or 0.0),
        )

    return _combined_state_from_results(
        query=state["query"],
        successful=successful,
        tools_used=tools_used,
        tool_trace=tool_trace,
        intent_source=state.get("planner_source", state.get("intent_source", "")),
    )


def _state_from_payload(
    payload: Dict[str, object],
    tools_used: list[str],
    tool_trace: List[Dict[str, Any]],
    *,
    intent: str | None = None,
    intent_source: str = "",
    intent_confidence: float = 0.0,
) -> AgentState:
    route = str(payload.get("route", ""))
    result_type = str(payload.get("result_type", route))
    return {
        "retrieval_payload": payload,
        "retrieved_contexts": payload.get("contexts", []),
        "citations": payload.get("citations", []),
        "tools_used": tools_used,
        "tool_trace": tool_trace,
        "route": route,
        "intent": intent if intent is not None else result_type,
        "intent_source": intent_source,
        "intent_confidence": intent_confidence,
        "result_type": result_type,
        "answer": payload.get("answer", ""),
        "risk_level": payload.get("risk_level"),
        "review_status": payload.get("review_status"),
        "review_id": payload.get("review_id"),
        "contract_review": payload.get("contract_review"),
    }


def _combined_state_from_results(
    *,
    query: str,
    successful: Sequence[Dict[str, Any]],
    tools_used: Sequence[str],
    tool_trace: List[Dict[str, Any]],
    intent_source: str,
) -> AgentState:
    citations: List[str] = []
    contexts: List[str] = []
    answer_parts: List[str] = []
    for result in successful:
        name = result["name"]
        payload = result.get("payload", {})
        citations.extend(str(item) for item in payload.get("citations", []) if item)
        contexts.extend(str(item) for item in payload.get("contexts", []) if item)
        answer = str(payload.get("answer") or "")
        if answer:
            label = "企业制度依据" if name == "search_company_policy" else "法律依据"
            answer_parts.append(f"{label}：{answer}")

    answer = "\n\n".join(answer_parts)
    if not answer:
        answer = "已调用相关工具，但未检索到可以支撑回答的明确依据。"
    return {
        "query": query,
        "answer": answer,
        "citations": _dedupe_keep_order(citations),
        "retrieved_contexts": _dedupe_keep_order(contexts),
        "tools_used": _dedupe_keep_order(tools_used),
        "tool_trace": tool_trace,
        "route": "compliance_qa",
        "intent": "compliance_qa",
        "intent_source": intent_source,
        "intent_confidence": 1.0,
        "result_type": "compliance_qa",
        "tool_results": list(successful),
    }


def _truncate(value: str, limit: int = 120) -> str:
    text = value.strip()
    return text if len(text) <= limit else f"{text[:limit]}..."


def _dedupe_keep_order(items: Iterable[Any]) -> List[Any]:
    seen = set()
    deduped = []
    for item in items:
        key = str(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped
