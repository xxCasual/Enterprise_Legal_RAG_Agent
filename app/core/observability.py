"""Small in-process metrics helpers for demo production readiness."""

from __future__ import annotations

from threading import Lock
from typing import Dict


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._values: Dict[str, float] = {
            "http_requests_total": 0.0,
            "http_request_duration_seconds_sum": 0.0,
            "tool_calls_total": 0.0,
            "tool_call_duration_seconds_sum": 0.0,
            "llm_failures_total": 0.0,
        }

    def increment(self, name: str, amount: float = 1.0) -> None:
        with self._lock:
            self._values[name] = self._values.get(name, 0.0) + amount

    def observe(self, name: str, value: float) -> None:
        self.increment(f"{name}_sum", value)

    def render_prometheus(self) -> str:
        with self._lock:
            snapshot = dict(self._values)
        lines = [
            "# HELP legal_rag_http_requests_total Total HTTP requests handled.",
            "# TYPE legal_rag_http_requests_total counter",
            f"legal_rag_http_requests_total {snapshot['http_requests_total']:.0f}",
            "# HELP legal_rag_http_request_duration_seconds_sum Total HTTP request latency.",
            "# TYPE legal_rag_http_request_duration_seconds_sum counter",
            (
                "legal_rag_http_request_duration_seconds_sum "
                f"{snapshot['http_request_duration_seconds_sum']:.6f}"
            ),
            "# HELP legal_rag_tool_calls_total Total agent tool calls.",
            "# TYPE legal_rag_tool_calls_total counter",
            f"legal_rag_tool_calls_total {snapshot['tool_calls_total']:.0f}",
            "# HELP legal_rag_tool_call_duration_seconds_sum Total agent tool latency.",
            "# TYPE legal_rag_tool_call_duration_seconds_sum counter",
            (
                "legal_rag_tool_call_duration_seconds_sum "
                f"{snapshot['tool_call_duration_seconds_sum']:.6f}"
            ),
            "# HELP legal_rag_llm_failures_total LLM failures that used fallback paths.",
            "# TYPE legal_rag_llm_failures_total counter",
            f"legal_rag_llm_failures_total {snapshot['llm_failures_total']:.0f}",
        ]
        return "\n".join(lines) + "\n"


metrics = MetricsRegistry()
