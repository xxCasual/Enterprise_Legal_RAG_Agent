"""Validate a running production stack; --no-llm avoids paid model requests.

Uploads a clearly synthetic policy and creates/approves a synthetic review.
Requires a running indexing worker, real embedding model and Chroma store.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    base = os.environ.get("BASE_URL", "http://localhost:8080").rstrip("/")
    token = os.environ.get("API_AUTH_TOKEN", "")

    def request(method, path, data=None, content_type="application/json", authenticated=True):
        headers = {"Content-Type": content_type}
        if token and authenticated:
            headers["X-API-Key"] = token
        if isinstance(data, dict):
            data = json.dumps(data).encode()
        req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
        with urllib.request.urlopen(req, timeout=args.timeout) as response:
            body = response.read().decode()
            return json.loads(body) if "application/json" in response.headers.get("Content-Type", "") else body

    health = request("GET", "/api/health")
    assert health["status"] == "ok", health
    ready = request("GET", "/api/ready")
    for name in ("database", "redis", "chroma"):
        assert ready["dependencies"][name]["status"] == "ok", ready
    if args.no_llm:
        assert ready["dependencies"]["model_api"]["status"] in {"ok", "degraded"}
    else:
        assert ready["status"] == "ok", ready

    boundary = "smoke-" + uuid4().hex
    policy = "自拟冒烟员工手册：工资发放日为每月十日。报销提交到财务审批。"
    upload = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="smoke_policy.txt"\r\nContent-Type: text/plain\r\n\r\n{policy}\r\n--{boundary}--\r\n').encode()
    record = request("POST", "/api/documents/upload", upload, f"multipart/form-data; boundary={boundary}")
    assert record["task_id"]
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        documents = request("GET", "/api/documents")["documents"]
        document = next(item for item in documents if item["doc_id"] == record["doc_id"])
        if document["status"] in {"ready", "failed"}:
            break
        time.sleep(1)
    else:
        raise AssertionError("Indexing worker did not finish before timeout")
    assert document["status"] == "ready" and document["chunk_count"] > 0, document
    policy_answer = request("POST", "/api/chat", {"query": "公司员工手册规定工资发放日是哪天？"})
    assert policy_answer["intent"] == "policy_qa", policy_answer
    assert any("每月十日" in context for context in policy_answer["citations"]), policy_answer
    review = request("POST", "/api/review/contract", {"contract_text": "甲方可随时解除合同且不支付经济补偿。乙方自愿放弃社保。", "include_evidence": False})
    assert review["review_status"] == "pending_review" and not review["findings"], review
    approved = request("POST", f"/api/reviews/{review['review_id']}/approve")
    assert approved["status"] == "approved" and approved["final_answer"]["findings"], approved
    if token:
        try:
            request("GET", "/api/documents", authenticated=False)
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
        else:
            raise AssertionError("Configured admin endpoint accepted unauthenticated request")
    metrics = request("GET", "/api/metrics")
    assert "http_requests_total" in metrics, metrics
    if not args.no_llm:
        law = request("POST", "/api/chat", {"query": "试用期最长多久？"})
        assert law["intent"] == "law_qa" and law["citations"], law
    report = {"model_mode": "no-key fallback; no model quality claim" if args.no_llm else "live model", "health": health, "readiness": ready, "doc_id": record["doc_id"], "task_id": record["task_id"], "document_status": document["status"], "chunk_count": document["chunk_count"], "policy_query_intent": policy_answer["intent"], "policy_citation_found": True, "review_id": review["review_id"], "review_status": approved["status"], "admin_auth_checked": bool(token), "metrics_checked": True}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("PRODUCTION SMOKE OK")


if __name__ == "__main__":
    main()
