"""Lightweight evaluation for the legal RAG pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Sequence

from evaluation.common import (
    latency_summary,
    load_json_cache,
    metric_summary,
    save_json_cache,
    write_csv_and_json,
)


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RAG_TESTSET_PATH = ROOT / "data" / "eval" / "testset.json"
RAG_RESULTS_DIR = ROOT / "data" / "eval" / "rag_results"
RAG_CACHE_PATH = RAG_RESULTS_DIR / "rag_eval_cache.json"

REQUIRED_FIELDS = ("question", "ground_truth", "reference_contexts")
ALLOWED_MODES = ("retrieval", "e2e")
RagRunner = Callable[[str, str], dict[str, Any]]


def load_rag_testset(path: Path | str = RAG_TESTSET_PATH) -> list[dict[str, Any]]:
    testset_path = Path(path)
    if not testset_path.exists():
        raise FileNotFoundError(f"RAG testset not found: {testset_path}")

    samples = json.loads(testset_path.read_text(encoding="utf-8"))
    if not isinstance(samples, list):
        raise ValueError("RAG testset must be a JSON list")

    for index, sample in enumerate(samples):
        _validate_sample(sample, index)
    return samples


def run_rag_eval(
    samples: Sequence[dict[str, Any]],
    *,
    mode: str = "retrieval",
    rag_runner: RagRunner | None = None,
    show_progress: bool = False,
    max_workers: int = 1,
    cache: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if mode not in ALLOWED_MODES:
        raise ValueError(f"mode must be one of {ALLOWED_MODES}")
    if max_workers < 1:
        raise ValueError("max_workers must be >= 1")

    runner = rag_runner or _default_rag_runner
    cache_lock = threading.Lock()

    if max_workers == 1:
        rows = []
        for index, sample in enumerate(samples):
            if show_progress:
                print(f">>> RAG Eval sample {index + 1}/{len(samples)} [{mode}]")
            row = _evaluate_sample(
                sample=sample,
                index=index,
                mode=mode,
                rag_runner=runner,
                cache=cache,
                cache_lock=cache_lock,
            )
            if show_progress:
                status = "failed" if row.get("error") else "ok"
                cache_text = " cache" if row.get("cache_hit") else ""
                print(f"    {status}{cache_text} in {row['latency']}s")
            rows.append(row)
        return rows, build_summary(rows, mode)

    rows_with_slots: list[dict[str, Any] | None] = [None] * len(samples)

    def run_one(index: int, sample: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        row = _evaluate_sample(
            sample=sample,
            index=index,
            mode=mode,
            rag_runner=runner,
            cache=cache,
            cache_lock=cache_lock,
        )
        return index, row

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(run_one, index, sample)
            for index, sample in enumerate(samples)
        ]
        for future in as_completed(futures):
            index, row = future.result()
            rows_with_slots[index] = row
            if show_progress:
                status = "failed" if row.get("error") else "ok"
                cache_text = " cache" if row.get("cache_hit") else ""
                print(
                    f">>> RAG Eval sample {index + 1}/{len(samples)} "
                    f"{status}{cache_text} in {row['latency']}s"
                )

    rows = [row for row in rows_with_slots if row is not None]
    return rows, build_summary(rows, mode)


def build_summary(rows: Sequence[dict[str, Any]], mode: str = "retrieval") -> dict[str, Any]:
    answer_values = (
        [row.get("answer_contains_ground_truth") for row in rows]
        if mode == "e2e"
        else []
    )
    total = len(rows)
    empty_count = sum(1 for row in rows if row.get("empty_context") is True)
    latency = latency_summary(rows)
    return {
        "mode": mode,
        "total_samples": total,
        "failed_samples": sum(1 for row in rows if row.get("error")),
        "cache_hits": sum(1 for row in rows if row.get("cache_hit")),
        "metrics": {
            "context_recall": metric_summary(
                [row.get("context_recall") for row in rows]
            ),
            "context_precision": metric_summary(
                [row.get("context_precision") for row in rows]
            ),
            "answer_contains_ground_truth": metric_summary(answer_values),
            "empty_context_rate": {
                "score": round(empty_count / total, 4) if total else None,
                "empty": empty_count,
                "valid_samples": total,
            },
            "avg_latency": latency.get("avg"),
            "p95_latency": latency.get("p95"),
        },
        "latency": latency,
        "failed_sample_ids": [row["sample_id"] for row in rows if row.get("error")],
    }


def save_results(
    rows: Sequence[dict[str, Any]],
    summary: dict[str, Any],
    *,
    results_dir: Path | str = RAG_RESULTS_DIR,
    tag: str | None = None,
) -> tuple[Path, Path]:
    fieldnames = [
        "sample_id",
        "mode",
        "question",
        "ground_truth",
        "reference_contexts",
        "actual_contexts",
        "answer",
        "context_recall",
        "context_precision",
        "answer_contains_ground_truth",
        "empty_context",
        "runner_latency",
        "latency",
        "cache_hit",
        "error",
        "raw_result",
    ]
    return write_csv_and_json(
        rows=rows,
        summary=summary,
        output_dir=results_dir,
        stem="rag_eval",
        fieldnames=fieldnames,
        tag=tag,
    )


def print_summary(summary: dict[str, Any]) -> None:
    print("\n" + "=" * 70)
    print("RAG Eval Summary")
    print("=" * 70)
    print(f"mode: {summary['mode']}")
    print(f"total_samples: {summary['total_samples']}")
    print(f"failed_samples: {summary['failed_samples']}")
    print(f"cache_hits: {summary.get('cache_hits', 0)}")
    print("\nMetrics")
    for metric_name, metric in summary["metrics"].items():
        if isinstance(metric, dict):
            score = metric.get("score")
            score_text = "n/a" if score is None else f"{score:.4f}"
            print(f"{metric_name}: {score_text}")
        else:
            print(f"{metric_name}: {metric}")
    print("=" * 70)


def warmup_rag(mode: str = "retrieval", rag_runner: RagRunner | None = None) -> None:
    runner = rag_runner or _default_rag_runner
    print(">>> Warming up RAG...")
    started_at = time.perf_counter()
    try:
        runner("试用期最长多久？", mode)
    except Exception as exc:
        print(f">>> RAG warmup failed: {type(exc).__name__}: {exc}")
        return
    print(f">>> RAG warmup finished in {round(time.perf_counter() - started_at, 3)}s")


def _evaluate_sample(
    *,
    sample: dict[str, Any],
    index: int,
    mode: str,
    rag_runner: RagRunner,
    cache: dict[str, Any] | None,
    cache_lock: threading.Lock,
) -> dict[str, Any]:
    _validate_sample(sample, index)
    question = sample["question"]
    ground_truth = sample["ground_truth"]
    reference_contexts = sample["reference_contexts"]
    row: dict[str, Any] = {
        "sample_id": index,
        "mode": mode,
        "question": question,
        "ground_truth": ground_truth,
        "reference_contexts": reference_contexts,
        "actual_contexts": [],
        "answer": "",
        "context_recall": None,
        "context_precision": None,
        "answer_contains_ground_truth": None,
        "empty_context": True,
        "runner_latency": None,
        "latency": 0,
        "cache_hit": False,
        "error": "",
        "raw_result": {},
    }
    started_at = time.perf_counter()
    result: dict[str, Any] = {}

    try:
        cache_key = _cache_key(sample, mode)
        if cache is not None and cache_key in cache:
            cached = cache[cache_key]
            row["cache_hit"] = True
            result = cached.get("result", {}) or {}
            row["error"] = cached.get("error", "") or ""
            row["runner_latency"] = cached.get("runner_latency")
        else:
            call_started_at = time.perf_counter()
            result = rag_runner(question, mode)
            runner_latency = _safe_float(result.get("latency"))
            if runner_latency is None:
                runner_latency = round(time.perf_counter() - call_started_at, 3)
            row["runner_latency"] = runner_latency
            if cache is not None:
                with cache_lock:
                    cache[cache_key] = {
                        "result": result,
                        "error": "",
                        "runner_latency": runner_latency,
                    }

        if not isinstance(result, dict):
            raise TypeError(f"RAG runner result must be a dict, got {type(result).__name__}")

        row["raw_result"] = result
        contexts = _extract_contexts(result)
        answer = str(result.get("answer") or "")
        row["actual_contexts"] = contexts
        row["answer"] = answer
        row["empty_context"] = len(contexts) == 0
        row["context_recall"] = _context_recall(reference_contexts, contexts)
        row["context_precision"] = _context_precision(reference_contexts, contexts)
        if mode == "e2e":
            row["answer_contains_ground_truth"] = _answer_contains_ground_truth(
                answer,
                ground_truth,
            )
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
        if cache is not None:
            with cache_lock:
                cache[_cache_key(sample, mode)] = {
                    "result": result if isinstance(result, dict) else {},
                    "error": row["error"],
                    "runner_latency": row.get("runner_latency"),
                }
    finally:
        row["latency"] = round(time.perf_counter() - started_at, 3)

    return row


def _default_rag_runner(question: str, mode: str) -> dict[str, Any]:
    from app.services.rag_service import rag_service

    return rag_service.retrieve(question) if mode == "retrieval" else rag_service.chat(question)


def _extract_contexts(result: dict[str, Any]) -> list[str]:
    raw_contexts = result.get("contexts") or result.get("citations") or []
    if isinstance(raw_contexts, str):
        return [raw_contexts] if raw_contexts.strip() else []
    if not isinstance(raw_contexts, Sequence):
        return [str(raw_contexts)]
    return [str(item) for item in raw_contexts if str(item).strip()]


def _context_recall(reference_contexts: Sequence[str], actual_contexts: Sequence[str]) -> float | None:
    references = [text for text in reference_contexts if str(text).strip()]
    if not references:
        return None
    matched = sum(
        1 for reference in references
        if any(_text_match(reference, actual) for actual in actual_contexts)
    )
    return round(matched / len(references), 4)


def _context_precision(reference_contexts: Sequence[str], actual_contexts: Sequence[str]) -> float | None:
    actuals = [text for text in actual_contexts if str(text).strip()]
    if not actuals:
        return 0.0
    matched = sum(
        1 for actual in actuals
        if any(_text_match(reference, actual) for reference in reference_contexts)
    )
    return round(matched / len(actuals), 4)


def _text_match(reference: str, actual: str) -> bool:
    left = _normalize_text(reference)
    right = _normalize_text(actual)
    if not left or not right:
        return False
    if left in right or right in left:
        return True
    left_terms = _terms(left)
    right_terms = _terms(right)
    if not left_terms:
        return False
    overlap = len(left_terms & right_terms) / len(left_terms)
    return overlap >= 0.65


def _answer_contains_ground_truth(answer: str, ground_truth: str) -> bool | None:
    truth = _normalize_text(ground_truth)
    if not truth:
        return None
    normalized_answer = _normalize_text(answer)
    if truth in normalized_answer:
        return True
    fragments = [fragment for fragment in re.split(r"[，。,、；;：:\s]+", ground_truth) if fragment]
    if not fragments:
        return False
    return all(_normalize_text(fragment) in normalized_answer for fragment in fragments)


def _terms(text: str) -> set[str]:
    if len(text) <= 24:
        return {text}
    return {text[index:index + 8] for index in range(0, len(text) - 7, 4)}


def _normalize_text(text: Any) -> str:
    return re.sub(r"\s+", "", str(text)).lower()


def _validate_sample(sample: dict[str, Any], index: int) -> None:
    missing = [field for field in REQUIRED_FIELDS if field not in sample]
    if missing:
        raise ValueError(f"Sample #{index} missing required fields: {missing}")
    if not isinstance(sample["question"], str) or not sample["question"].strip():
        raise ValueError(f"Sample #{index} question must be a non-empty string")
    if not isinstance(sample["ground_truth"], str):
        raise ValueError(f"Sample #{index} ground_truth must be a string")
    if not isinstance(sample["reference_contexts"], list):
        raise ValueError(f"Sample #{index} reference_contexts must be a list")


def _cache_key(sample: dict[str, Any], mode: str) -> str:
    payload = {
        "mode": mode,
        "question": sample["question"],
        "ground_truth": sample["ground_truth"],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run legal RAG evaluation.")
    parser.add_argument("--testset", type=Path, default=RAG_TESTSET_PATH)
    parser.add_argument("--mode", choices=ALLOWED_MODES, default="retrieval")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--tag", type=str, default=None)
    parser.add_argument("--output-dir", type=Path, default=RAG_RESULTS_DIR)
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument("--warmup", action="store_true")
    parser.add_argument("--cache", action="store_true")
    parser.add_argument("--cache-path", type=Path, default=RAG_CACHE_PATH)
    args = parser.parse_args()

    samples = load_rag_testset(args.testset)
    if args.limit is not None:
        samples = samples[: args.limit]

    print("=" * 70)
    print(f"mode: {args.mode}")
    print(f"total_samples: {len(samples)}")
    print(f"max_workers: {args.max_workers}")
    print(f"cache: {args.cache}")
    print("=" * 70)

    if args.warmup:
        warmup_rag(args.mode)

    cache = load_json_cache(args.cache_path) if args.cache else None
    rows, summary = run_rag_eval(
        samples,
        mode=args.mode,
        show_progress=True,
        max_workers=args.max_workers,
        cache=cache,
    )
    if args.cache and cache is not None:
        save_json_cache(cache, args.cache_path)
        print(f"\n>>> Cache saved: {args.cache_path}")

    csv_path, json_path = save_results(
        rows,
        summary,
        results_dir=args.output_dir,
        tag=args.tag,
    )
    print_summary(summary)
    print(f"\n>>> CSV saved: {csv_path}")
    print(f">>> JSON saved: {json_path}")


if __name__ == "__main__":
    main()

