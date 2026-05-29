"""LLM and fallback tool planning for the agent graph."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.agent.constants import PLANNER_SYSTEM_PROMPT, PUBLIC_TOOL_NAMES, TOOL_BY_INTENT
from app.agent.guards import _is_compliance_combo_query
from app.agent.intent_classifier import IntentClassifier
from app.agent.state import AgentState
from app.agent.tools import registered_agent_tools
from app.core.config import settings
from app.core.observability import metrics


fallback_intent_classifier = IntentClassifier()


def tool_planner_node(state: AgentState) -> AgentState:
    return build_tool_plan_state(state, plan_tools_with_llm)


def build_tool_plan_state(state: AgentState, planner_func=None) -> AgentState:
    query = state["query"]
    allowed_tools = state.get("allowed_tools") or list(PUBLIC_TOOL_NAMES)
    planner = planner_func or plan_tools_with_llm
    try:
        tool_calls = planner(query, allowed_tools)
        tool_calls = _normalize_tool_calls(tool_calls, allowed_tools, query)
        if tool_calls:
            return {
                "tool_calls": tool_calls,
                "planner_source": "llm_tool_call",
            }
    except Exception:
        metrics.increment("llm_failures_total")
        pass

    return {
        "tool_calls": _fallback_tool_calls(query, allowed_tools),
        "planner_source": "fallback",
    }


def plan_tools_with_llm(
    query: str,
    allowed_tools: Sequence[str] | None = None,
) -> List[Dict[str, Any]]:
    if not settings.deepseek_api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")

    allowed = set(allowed_tools or PUBLIC_TOOL_NAMES)
    tools = [
        tool
        for tool in registered_agent_tools()
        if getattr(tool, "name", "") in allowed
    ]
    if not tools:
        return []

    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        timeout=settings.llm_timeout_seconds,
        max_retries=2,
    ).bind_tools(tools)
    message = llm.invoke(
        [
            SystemMessage(content=PLANNER_SYSTEM_PROMPT),
            HumanMessage(content=query),
        ]
    )
    return _tool_calls_from_message(message)


def _fallback_tool_calls(
    query: str,
    allowed_tools: Sequence[str],
) -> List[Dict[str, Any]]:
    allowed = set(allowed_tools)
    if _is_compliance_combo_query(query) and {
        "search_company_policy",
        "search_law_articles",
    }.issubset(allowed):
        return [
            {"name": "search_company_policy", "args": {"query": query}},
            {"name": "search_law_articles", "args": {"query": query}},
        ]

    result = fallback_intent_classifier.classify(query)
    tool_name = TOOL_BY_INTENT.get(result.intent, "refuse_out_of_scope")
    if tool_name not in allowed:
        tool_name = next(iter(allowed), "refuse_out_of_scope")
    arg_name = "contract_text" if tool_name == "contract_review_rules" else "query"
    return [{"name": tool_name, "args": {arg_name: query}}]


def _tool_calls_from_message(message: Any) -> List[Dict[str, Any]]:
    raw_calls = getattr(message, "tool_calls", None) or []
    if raw_calls:
        return [
            {
                "name": str(call.get("name", "")),
                "args": call.get("args") or {},
                "id": call.get("id"),
            }
            for call in raw_calls
            if call.get("name")
        ]

    additional_kwargs = getattr(message, "additional_kwargs", {}) or {}
    openai_calls = additional_kwargs.get("tool_calls") or []
    normalized = []
    for call in openai_calls:
        function = call.get("function", {}) if isinstance(call, dict) else {}
        name = function.get("name")
        if not name:
            continue
        normalized.append({"name": name, "args": function.get("arguments") or {}})
    return normalized


def _normalize_tool_calls(
    tool_calls: Iterable[Dict[str, Any]],
    allowed_tools: Sequence[str],
    query: str,
) -> List[Dict[str, Any]]:
    allowed = set(allowed_tools)
    normalized = []
    seen = set()
    for call in tool_calls:
        name = str(call.get("name") or "")
        if name not in allowed or name not in PUBLIC_TOOL_NAMES:
            continue
        args = call.get("args") or {}
        if isinstance(args, str):
            args = {"query": args}
        if not isinstance(args, dict):
            args = {}
        args = _coerce_tool_args(name, args, query)
        key = (name, tuple(sorted((str(k), str(v)) for k, v in args.items())))
        if key in seen:
            continue
        seen.add(key)
        normalized.append({"name": name, "args": args})
    return normalized


def _coerce_tool_args(name: str, args: Dict[str, Any], query: str) -> Dict[str, Any]:
    if name == "contract_review_rules":
        text = args.get("contract_text") or args.get("query") or query
        return {"contract_text": str(text)}
    text = args.get("query") or args.get("question") or query
    return {"query": str(text)}
