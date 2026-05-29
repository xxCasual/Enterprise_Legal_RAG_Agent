"""Dependency readiness checks for production deployments."""

from __future__ import annotations

from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine
from app.rag.chroma_client import chroma_health


def collect_readiness() -> dict:
    dependencies = {
        "database": _database_status(),
        "redis": _redis_status(),
        "chroma": _chroma_status(),
        "model_api": _model_status(),
    }
    document_summary = _document_summary()
    dependencies.update(document_summary.get("dependencies", {}))
    status = "ok" if all(_is_ok(item) for item in dependencies.values()) else "degraded"
    return {
        "status": status,
        "dependencies": dependencies,
        "document_counts": document_summary.get("document_counts", {}),
    }


def _database_status() -> dict:
    if not settings.database_url:
        return {"status": "not_configured", "detail": "using local JSON fallback"}
    if engine is None:
        return {"status": "error", "detail": "database engine not initialized"}
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "detail": "connected"}
    except Exception as exc:
        return {"status": "error", "detail": f"{type(exc).__name__}: {exc}"}


def _redis_status() -> dict:
    if not settings.redis_url:
        return {"status": "not_configured", "detail": "document indexing runs inline"}
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=1)
        client.ping()
        return {"status": "ok", "detail": "connected"}
    except Exception as exc:
        return {"status": "error", "detail": f"{type(exc).__name__}: {exc}"}


def _chroma_status() -> dict:
    status, detail = chroma_health()
    return {"status": status, "detail": detail}


def _model_status() -> dict:
    if settings.deepseek_api_key:
        return {"status": "ok", "detail": settings.llm_model}
    return {"status": "degraded", "detail": "DEEPSEEK_API_KEY is not configured"}


def _document_summary() -> dict:
    try:
        from app.services.document_service import document_service

        return {"document_counts": document_service.status_counts(), "dependencies": {}}
    except Exception as exc:
        return {
            "document_counts": {},
            "dependencies": {
                "document_registry": {
                    "status": "error",
                    "detail": f"{type(exc).__name__}: {exc}",
                }
            },
        }


def _is_ok(item: dict) -> bool:
    return item.get("status") in {"ok", "not_configured"}
