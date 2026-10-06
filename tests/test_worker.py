"""Retry boundaries use the real document/task repository and parsing flow."""
from __future__ import annotations

from collections import deque
from dataclasses import replace

from app import worker
from app.services import document_service as document_module
from app.services.document_service import DocumentService


class Queue:
    def __init__(self):
        self.messages = deque()

    def enqueue(self, message):
        self.messages.append(message)

    def dequeue(self, timeout_seconds=5):
        return self.messages.popleft() if self.messages else None


class Index:
    def __init__(self, failures):
        self.failures = failures
        self.documents = []

    def add_documents(self, documents):
        if self.failures:
            self.failures -= 1
            raise TimeoutError("controlled vector service outage")
        self.documents.extend(documents)


def setup_service(tmp_path, monkeypatch, failures):
    queue = Queue()
    service = DocumentService(uploads_dir=tmp_path / "uploads", registry_path=tmp_path / "documents.json", persist_dir=tmp_path / "vectors")
    index = Index(failures)
    monkeypatch.setattr(service, "_get_vectorstore", lambda: index)
    monkeypatch.setattr(document_module, "create_indexing_queue", lambda: queue)
    monkeypatch.setattr(worker, "create_indexing_queue", lambda: queue)
    monkeypatch.setattr(worker, "document_service", service)
    monkeypatch.setattr(worker, "settings", replace(worker.settings, indexing_max_attempts=3))
    record = service.submit_upload("policy.txt", "工资发放日为每月十日。".encode())
    return service, queue, index, record


def test_transient_indexing_failure_is_retried_and_persists_success(tmp_path, monkeypatch):
    service, queue, index, record = setup_service(tmp_path, monkeypatch, failures=1)
    assert worker.process_once(timeout_seconds=1)
    assert service.repository.get_document(record["doc_id"])["status"] == "pending"
    assert service.repository.get_task(record["task_id"])["attempts"] == 1
    assert len(queue.messages) == 1
    assert worker.process_once(timeout_seconds=1)
    reloaded = DocumentService(uploads_dir=tmp_path / "uploads", registry_path=tmp_path / "documents.json", persist_dir=tmp_path / "vectors")
    document = reloaded.repository.get_document(record["doc_id"])
    task = reloaded.repository.get_task(record["task_id"])
    assert document["status"] == "ready" and document["chunk_count"] == len(index.documents) == 1
    assert task["status"] == "succeeded" and task["attempts"] == 2 and task["last_error"] is None
    assert not queue.messages


def test_indexing_failure_stops_at_max_attempts_with_saved_error(tmp_path, monkeypatch):
    service, queue, index, record = setup_service(tmp_path, monkeypatch, failures=10)
    for _ in range(3):
        assert worker.process_once(timeout_seconds=1)
    task = service.repository.get_task(record["task_id"])
    document = service.repository.get_document(record["doc_id"])
    assert task["status"] == document["status"] == "failed"
    assert task["attempts"] == 3
    assert "TimeoutError" in task["last_error"] and "TimeoutError" in document["error_message"]
    assert not queue.messages and not index.documents
