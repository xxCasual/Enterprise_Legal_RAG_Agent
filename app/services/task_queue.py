"""Redis-backed indexing queue with an inline fallback for local development."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict

from app.core.config import settings


QUEUE_NAME = "legal_rag:indexing"


@dataclass(frozen=True)
class IndexingMessage:
    task_id: str
    doc_id: str

    def to_json(self) -> str:
        return json.dumps({"task_id": self.task_id, "doc_id": self.doc_id})

    @classmethod
    def from_json(cls, value: str | bytes) -> "IndexingMessage":
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        data: Dict[str, Any] = json.loads(value)
        return cls(task_id=str(data["task_id"]), doc_id=str(data["doc_id"]))


class RedisIndexingQueue:
    def __init__(self, redis_url: str | None = None, queue_name: str = QUEUE_NAME) -> None:
        self.redis_url = redis_url or settings.redis_url
        if not self.redis_url:
            raise RuntimeError("REDIS_URL is not configured")
        import redis

        self.client = redis.Redis.from_url(self.redis_url, socket_timeout=15)
        self.queue_name = queue_name

    def enqueue(self, message: IndexingMessage) -> None:
        self.client.rpush(self.queue_name, message.to_json())

    def dequeue(self, timeout_seconds: int = 5) -> IndexingMessage | None:
        try:
            item = self.client.blpop(self.queue_name, timeout=timeout_seconds)
        except TimeoutError:
            return None
        except Exception as exc:
            if exc.__class__.__name__ == "TimeoutError":
                return None
            raise
        if not item:
            return None
        _, payload = item
        return IndexingMessage.from_json(payload)


def create_indexing_queue() -> RedisIndexingQueue | None:
    if not settings.redis_url:
        return None
    return RedisIndexingQueue(settings.redis_url)
