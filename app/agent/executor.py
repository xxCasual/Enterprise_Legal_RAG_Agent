"""Tool execution and trace generation for the agent graph."""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Iterable, List

from app.agent.constants import PUBLIC_TOOL_NAMES
from app.agent.planner import _normalize_tool_calls
from app.agent.state import AgentState
from app.agent.tools import (
    refuse_out_of_scope,
    review_labor_contract,
    search_company_policy,
    search_law_articles,
)
from app.core.observability import metrics


ToolExecutor = Callable[[str, Dict[str, Any], str], Dict[str, Any]]


def tool_executor_node(state: AgentState) -> AgentState:
    return execute_tool_state(state, _execute_tool)


def execute_tool_state(
    state: AgentState,
    execute_tool: ToolExecutor,
) -> AgentState:
    query = state["query"]
    tool_calls = _normalize_tool_calls(
        state.get("tool_calls", []),
        state.get("allowed_tools") or PUBLIC_TOOL_NAMES,
        query,
    )
    tool_results: List[Dict[str, Any]] = []
    tool_trace: List[Dict[str, Any]] = []
    tools_used: List[str] = []

    for call in tool_calls:
        name = call["name"]
        args = dict(call.get("args") or {})
        started_at = time.perf_counter()
        trace = {
            "name": name,
            "args": _trace_args(args),
            "status": "ok",
            "latency": 0.0,
        }
        try:
            payload = execute_tool(name, args, query)
            tools_used.append(name)
            tool_results.append(
                {
                    "name": name,
                    "args": args,
                    "status": "ok",
                    "payload": payload,
                }
            )
            trace["route"] = payload.get("route", "")
            trace["result_type"] = payload.get("result_type", payload.get("route", ""))
            if payload.get("risk_level") is not None:
                trace["risk_level"] = payload.get("risk_level")
            if payload.get("review_status") is not None:
                trace["review_status"] = payload.get("review_status")
            if payload.get("answer_source") is not None:
                trace["answer_source"] = payload.get("answer_source")
            if payload.get("context_count") is not None:
                trace["context_count"] = payload.get("context_count")
        except Exception as exc:
            tool_results.append(
                {
                    "name": name,
                    "args": args,
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                    "payload": {},
                }
            )
            trace["status"] = "error"
            trace["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            trace["latency"] = round(time.perf_counter() - started_at, 3)
            metrics.increment("tool_calls_total")
            metrics.observe("tool_call_duration_seconds", trace["latency"])
            tool_trace.append(trace)

    return {
        "tool_calls": tool_calls,
        "tool_results": tool_results,
        "tool_trace": tool_trace,
        "tools_used": _dedupe_keep_order(tools_used),
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


def _trace_args(args: Dict[str, Any]) -> Dict[str, str]:
    return {str(key): _truncate(str(value)) for key, value in args.items()}


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
