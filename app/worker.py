"""Background worker for enterprise policy document indexing."""

from __future__ import annotations

import json
import logging
import time

from app.core.config import settings
from app.core.database import init_database
from app.core.logging import configure_logging
from app.services.document_service import document_service
from app.services.task_queue import IndexingMessage, create_indexing_queue


configure_logging()
logger = logging.getLogger("legal_rag.worker")


def process_once(timeout_seconds: int = 5) -> bool:
    queue = create_indexing_queue()
    if queue is None:
        logger.info(json.dumps({"event": "worker_idle", "detail": "REDIS_URL not configured"}))
        time.sleep(timeout_seconds)
        return False
    message = queue.dequeue(timeout_seconds=timeout_seconds)
    if message is None:
        return False
    logger.info(
        json.dumps(
            {
                "event": "indexing_task_started",
                "task_id": message.task_id,
                "doc_id": message.doc_id,
            }
        )
    )
    try:
        document_service.process_indexing_task(message.task_id)
        logger.info(
            json.dumps(
                {
                    "event": "indexing_task_succeeded",
                    "task_id": message.task_id,
                    "doc_id": message.doc_id,
                }
            )
        )
    except Exception as exc:
        task = document_service.repository.get_task(message.task_id)
        attempts = int(task.get("attempts") or 0)
        if attempts < settings.indexing_max_attempts:
            document_service.repository.update_document(
                message.doc_id,
                {
                    "status": "pending",
                    "error_message": f"{type(exc).__name__}: {exc}",
                },
            )
            document_service.repository.update_task(
                message.task_id,
                {
                    "status": "pending",
                    "updated_at": document_service._now(),
                    "last_error": f"{type(exc).__name__}: {exc}",
                },
            )
            queue.enqueue(IndexingMessage(task_id=message.task_id, doc_id=message.doc_id))
        logger.exception(
            json.dumps(
                {
                    "event": "indexing_task_failed",
                    "task_id": message.task_id,
                    "doc_id": message.doc_id,
                    "attempts": attempts,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        )
    return True


def main() -> None:
    init_database()
    logger.info(json.dumps({"event": "worker_started"}))
    while True:
        process_once(timeout_seconds=5)


if __name__ == "__main__":
    main()
