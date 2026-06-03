"""Lightweight checks for RAG Eval metrics and outputs."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import evaluation.rag.core as rag_eval  # noqa: E402


def _sample(
    question: str = "试用期最长多久？",
    ground_truth: str = "六个月",
    reference_contexts: list[str] | None = None,
):
    return {
        "question": question,
        "ground_truth": ground_truth,
        "reference_contexts": reference_contexts or ["试用期不得超过六个月"],
    }


def test_rag_eval_validates_required_fields() -> None:
    with TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "bad_rag_testset.json"
        path.write_text(json.dumps([{"question": "缺少字段"}]), encoding="utf-8")

        try:
            rag_eval.load_rag_testset(path)
        except ValueError as exc:
            assert "missing required fields" in str(exc)
        else:
            raise AssertionError("invalid RAG Eval samples should be rejected")


def test_rag_eval_retrieval_metrics_match_reference_contexts() -> None:
    samples = [_sample()]

    def fake_rag_runner(question: str, mode: str):
        assert question == "试用期最长多久？"
        assert mode == "retrieval"
        return {
            "contexts": ["根据劳动合同法第十九条，试用期不得超过六个月。"],
            "latency": 0.01,
        }

    rows, summary = rag_eval.run_rag_eval(
        samples,
        mode="retrieval",
        rag_runner=fake_rag_runner,
    )

    assert rows[0]["context_recall"] == 1.0
    assert rows[0]["context_precision"] == 1.0
    assert rows[0]["answer_contains_ground_truth"] is None
    assert summary["metrics"]["context_recall"]["score"] == 1.0
    assert summary["metrics"]["empty_context_rate"]["score"] == 0.0


def test_rag_eval_e2e_checks_answer_ground_truth() -> None:
    samples = [_sample()]

    def fake_rag_runner(_: str, mode: str):
        assert mode == "e2e"
        return {
            "answer": "劳动合同法规定，试用期最长不得超过六个月。",
            "citations": ["试用期不得超过六个月"],
            "latency": 0.02,
        }

    rows, summary = rag_eval.run_rag_eval(
        samples,
        mode="e2e",
        rag_runner=fake_rag_runner,
    )

    assert rows[0]["answer_contains_ground_truth"] is True
    assert summary["metrics"]["answer_contains_ground_truth"]["score"] == 1.0


def test_rag_eval_handles_empty_contexts() -> None:
    samples = [_sample()]

    rows, summary = rag_eval.run_rag_eval(
        samples,
        mode="retrieval",
        rag_runner=lambda *_: {"contexts": [], "latency": 0.01},
    )

    assert rows[0]["empty_context"] is True
    assert rows[0]["context_recall"] == 0.0
    assert rows[0]["context_precision"] == 0.0
    assert summary["metrics"]["empty_context_rate"]["score"] == 1.0


def test_rag_eval_saves_csv_and_json_summary() -> None:
    rows = [
        {
            "sample_id": 0,
            "mode": "retrieval",
            "question": "试用期最长多久？",
            "ground_truth": "六个月",
            "reference_contexts": ["试用期不得超过六个月"],
            "actual_contexts": ["试用期不得超过六个月"],
            "answer": "",
            "context_recall": 1.0,
            "context_precision": 1.0,
            "answer_contains_ground_truth": None,
            "empty_context": False,
            "runner_latency": 0.01,
            "latency": 0.01,
            "cache_hit": False,
            "error": "",
            "raw_result": {},
        }
    ]
    summary = rag_eval.build_summary(rows)

    with TemporaryDirectory() as temp_dir:
        csv_path, json_path = rag_eval.save_results(
            rows,
            summary,
            results_dir=Path(temp_dir),
            tag="unit",
        )

        assert csv_path.exists()
        assert json_path.exists()
        assert "rag_eval_unit_" in csv_path.name
        saved_summary = json.loads(json_path.read_text(encoding="utf-8"))
        assert saved_summary["csv_path"] == str(csv_path)
        assert saved_summary["metrics"]["context_recall"]["score"] == 1.0


def test_rag_eval_cache_reuses_runner_result() -> None:
    samples = [_sample()]
    calls = {"count": 0}
    cache = {}

    def fake_rag_runner(_: str, __: str):
        calls["count"] += 1
        return {"contexts": ["试用期不得超过六个月"], "latency": 0.01}

    rag_eval.run_rag_eval(samples, rag_runner=fake_rag_runner, cache=cache)
    rows, _ = rag_eval.run_rag_eval(samples, rag_runner=fake_rag_runner, cache=cache)

    assert calls["count"] == 1
    assert rows[0]["cache_hit"] is True

