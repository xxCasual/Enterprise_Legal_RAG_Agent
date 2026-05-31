"""Small in-process metrics helpers for demo production readiness."""

from __future__ import annotations

from threading import Lock
from typing import Dict, Mapping


class MetricsRegistry:
    HISTOGRAM_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 120.0)

    def __init__(self) -> None:
        self._lock = Lock()
        self._values: Dict[str, float] = {
            "http_requests_total": 0.0,
            "http_request_duration_seconds_sum": 0.0,
            "http_request_duration_seconds_count": 0.0,
            "tool_calls_total": 0.0,
            "tool_call_duration_seconds_sum": 0.0,
            "tool_call_duration_seconds_count": 0.0,
            "llm_failures_total": 0.0,
        }
        self._labeled_values: Dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}

    def increment(
        self,
        name: str,
        amount: float = 1.0,
        *,
        labels: Mapping[str, object] | None = None,
    ) -> None:
        with self._lock:
            if labels:
                key = (name, _label_items(labels))
                self._labeled_values[key] = self._labeled_values.get(key, 0.0) + amount
            else:
                self._values[name] = self._values.get(name, 0.0) + amount

    def observe(
        self,
        name: str,
        value: float,
        *,
        labels: Mapping[str, object] | None = None,
    ) -> None:
        self.increment(f"{name}_sum", value, labels=labels)
        self.increment(f"{name}_count", 1.0, labels=labels)
        if labels:
            for bucket in self.HISTOGRAM_BUCKETS:
                if value <= bucket:
                    self.increment(
                        f"{name}_bucket",
                        1.0,
                        labels={**labels, "le": _format_bucket(bucket)},
                    )
            self.increment(
                f"{name}_bucket",
                1.0,
                labels={**labels, "le": "+Inf"},
            )

    def render_prometheus(self) -> str:
        with self._lock:
            snapshot = dict(self._values)
            labeled_snapshot = dict(self._labeled_values)
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
            "legal_rag_http_request_duration_seconds_count "
            f"{snapshot['http_request_duration_seconds_count']:.0f}",
            "# HELP legal_rag_tool_calls_total Total agent tool calls.",
            "# TYPE legal_rag_tool_calls_total counter",
            f"legal_rag_tool_calls_total {snapshot['tool_calls_total']:.0f}",
            "# HELP legal_rag_tool_call_duration_seconds_sum Total agent tool latency.",
            "# TYPE legal_rag_tool_call_duration_seconds_sum counter",
            (
                "legal_rag_tool_call_duration_seconds_sum "
                f"{snapshot['tool_call_duration_seconds_sum']:.6f}"
            ),
            "legal_rag_tool_call_duration_seconds_count "
            f"{snapshot['tool_call_duration_seconds_count']:.0f}",
            "# HELP legal_rag_llm_failures_total LLM failures that used fallback paths.",
            "# TYPE legal_rag_llm_failures_total counter",
            f"legal_rag_llm_failures_total {snapshot['llm_failures_total']:.0f}",
        ]
        for (name, labels), value in sorted(labeled_snapshot.items()):
            lines.append(f"legal_rag_{name}{_render_labels(labels)} {value:.6f}")
        return "\n".join(lines) + "\n"


def _label_items(labels: Mapping[str, object]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((str(key), str(value)) for key, value in labels.items()))


def _render_labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    rendered = ",".join(f'{key}="{_escape_label(value)}"' for key, value in labels)
    return "{" + rendered + "}"


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _format_bucket(value: float) -> str:
    return f"{value:g}"


metrics = MetricsRegistry()
