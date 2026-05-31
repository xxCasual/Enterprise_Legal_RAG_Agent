"""Mixed HTTP stress checks for the production-like stack.

The default scenarios avoid high-volume external LLM calls. Set
RUN_REAL_RAG=1 to add a small warm legal RAG sample.
"""

from __future__ import annotations

import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request

BASE_URL = os.getenv("BASE_URL", "http://localhost:8080").rstrip("/")
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN", "")
OUT = Path(os.getenv("STRESS_OUT", "data/eval/agent_results/stress_mixed.json"))
RUN_REAL_RAG = os.getenv("RUN_REAL_RAG", "0").strip().lower() in {"1", "true", "yes", "on"}

LOW_RISK_CONTRACT = (
    "合同期限为三年。试用期三个月。工资为每月八千元。"
    "执行标准工时。公司依法缴纳社会保险。双方依法解除或终止劳动合同。"
)


@dataclass(frozen=True)
class Scenario:
    name: str
    method: str
    path: str
    total: int
    concurrency: int
    body: dict[str, Any] | None = None
    auth: bool = False
    timeout: float = 30.0


def call(scenario: Scenario) -> dict[str, Any]:
    headers = {"Connection": "close"}
    data = None
    if scenario.body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(scenario.body, ensure_ascii=False).encode("utf-8")
    if scenario.auth and API_AUTH_TOKEN:
        headers["X-API-Key"] = API_AUTH_TOKEN

    started_at = time.perf_counter()
    status = 0
    size = 0
    err = ""
    try:
        req = request.Request(
            BASE_URL + scenario.path,
            data=data,
            headers=headers,
            method=scenario.method,
        )
        with request.urlopen(req, timeout=scenario.timeout) as resp:
            status = resp.status
            size = len(resp.read())
    except error.HTTPError as exc:
        status = exc.code
        size = len(exc.read())
        err = f"HTTPError: {exc}"
    except Exception as exc:  # pragma: no cover - operational script
        err = f"{type(exc).__name__}: {exc}"
    return {
        "status": status,
        "latency": time.perf_counter() - started_at,
        "bytes": size,
        "error": err,
    }


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[int(round((len(ordered) - 1) * pct))]


def run_scenario(scenario: Scenario) -> dict[str, Any]:
    for _ in range(min(3, scenario.total)):
        call(scenario)
    started_at = time.perf_counter()
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=scenario.concurrency) as pool:
        futures = [pool.submit(call, scenario) for _ in range(scenario.total)]
        for future in as_completed(futures):
            results.append(future.result())
    elapsed = time.perf_counter() - started_at
    latencies = [result["latency"] for result in results]
    ok = sum(1 for result in results if 200 <= result["status"] < 300 and not result["error"])
    status_counts: dict[str, int] = {}
    errors: dict[str, int] = {}
    for result in results:
        status_counts[str(result["status"])] = status_counts.get(str(result["status"]), 0) + 1
        if result["error"]:
            errors[result["error"]] = errors.get(result["error"], 0) + 1
    return {
        "name": scenario.name,
        "method": scenario.method,
        "path": scenario.path,
        "total": scenario.total,
        "concurrency": scenario.concurrency,
        "elapsed": round(elapsed, 4),
        "rps": round(scenario.total / elapsed, 2) if elapsed else 0,
        "ok": ok,
        "error_count": scenario.total - ok,
        "status_counts": status_counts,
        "errors": errors,
        "latency_seconds": {
            "avg": round(statistics.mean(latencies), 4) if latencies else 0,
            "p50": round(percentile(latencies, 0.50), 4),
            "p95": round(percentile(latencies, 0.95), 4),
            "p99": round(percentile(latencies, 0.99), 4),
            "max": round(max(latencies), 4) if latencies else 0,
        },
    }


def main() -> None:
    scenarios = [
        Scenario("health", "GET", "/api/health", total=200, concurrency=40, timeout=10),
        Scenario("ready", "GET", "/api/ready", total=60, concurrency=12, timeout=20),
        Scenario("documents", "GET", "/api/documents", total=80, concurrency=16, auth=True, timeout=20),
        Scenario(
            "chat_contract_rules",
            "POST",
            "/api/chat",
            total=60,
            concurrency=12,
            body={"query": LOW_RISK_CONTRACT},
            timeout=30,
        ),
    ]
    if RUN_REAL_RAG:
        scenarios.append(
            Scenario(
                "chat_law_real_small",
                "POST",
                "/api/chat",
                total=5,
                concurrency=1,
                body={"query": "劳动仲裁的时效一般是多久？"},
                timeout=180,
            )
        )

    summary = {
        "base_url": BASE_URL,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scenarios": [],
    }
    for scenario in scenarios:
        print(f">>> {scenario.name}: total={scenario.total} concurrency={scenario.concurrency}")
        result = run_scenario(scenario)
        summary["scenarios"].append(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"WROTE {OUT}")


if __name__ == "__main__":
    main()
