"""Common result, cache, and metric helpers for evaluation modules."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence


def csv_value(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return ""
    return value


def metric_summary(values: Sequence[float | bool | None]) -> dict[str, Any]:
    valid = [value for value in values if value is not None]
    if not valid:
        return {"score": None, "correct": 0, "valid_samples": 0}

    if all(isinstance(value, bool) for value in valid):
        correct = sum(1 for value in valid if value is True)
        score = correct / len(valid)
    else:
        numeric = [float(value) for value in valid]
        score = sum(numeric) / len(numeric)
        correct = sum(1 for value in numeric if value >= 1.0)

    return {
        "score": round(score, 4),
        "correct": correct,
        "valid_samples": len(valid),
    }


def latency_summary(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    valid_rows = [row for row in rows if not row.get("error")]
    latencies = [float(row["latency"]) for row in valid_rows]
    if not latencies:
        return {"avg": None, "p95": None, "max": None, "slowest_samples": []}

    sorted_latencies = sorted(latencies)
    p95_index = max(int(len(sorted_latencies) * 0.95) - 1, 0)
    slowest_samples = sorted(
        [
            {
                "sample_id": row["sample_id"],
                "latency": row["latency"],
                "query": row.get("question") or row.get("query") or "",
            }
            for row in valid_rows
        ],
        key=lambda item: item["latency"],
        reverse=True,
    )[:5]
    return {
        "avg": round(sum(latencies) / len(latencies), 3),
        "p95": sorted_latencies[p95_index],
        "max": max(latencies),
        "slowest_samples": slowest_samples,
    }


def load_json_cache(path: Path | str) -> dict[str, Any]:
    cache_path = Path(path)
    if not cache_path.exists():
        return {}
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def save_json_cache(cache: dict[str, Any], path: Path | str) -> None:
    cache_path = Path(path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_csv_and_json(
    *,
    rows: Sequence[dict[str, Any]],
    summary: dict[str, Any],
    output_dir: Path | str,
    stem: str,
    fieldnames: Sequence[str],
    tag: str | None = None,
) -> tuple[Path, Path]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{tag}" if tag else ""
    csv_path = directory / f"{stem}{suffix}_{timestamp}.csv"
    json_path = directory / f"{stem}{suffix}_{timestamp}.json"

    with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: csv_value(row.get(name)) for name in fieldnames})

    json_path.write_text(
        json.dumps({**summary, "csv_path": str(csv_path)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return csv_path, json_path

