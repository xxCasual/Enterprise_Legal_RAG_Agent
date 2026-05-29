"""Chroma client factory shared by RAG and document indexing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.config import settings


def create_chroma_client(persist_dir: Path | str) -> Any:
    import chromadb

    if settings.chroma_host:
        return chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
    return chromadb.PersistentClient(path=str(persist_dir))


def chroma_health() -> tuple[str, str]:
    try:
        if settings.chroma_host:
            client = create_chroma_client(settings.llama_company_chroma_persist_dir)
            heartbeat = getattr(client, "heartbeat", None)
            if callable(heartbeat):
                heartbeat()
            return "ok", f"{settings.chroma_host}:{settings.chroma_port}"
        settings.llama_law_chroma_persist_dir.mkdir(parents=True, exist_ok=True)
        settings.llama_company_chroma_persist_dir.mkdir(parents=True, exist_ok=True)
        return "ok", "local_persistent_client"
    except Exception as exc:
        return "error", f"{type(exc).__name__}: {exc}"
