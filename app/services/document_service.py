"""Upload, parse, split, index, and track company policy documents."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Iterable, List, Protocol
from uuid import uuid4

from sqlalchemy import select

from app.core.config import settings
from app.core.database import DocumentModel, IndexingTaskModel, session_scope
from app.services.task_queue import IndexingMessage, create_indexing_queue


DOCUMENT_PENDING = "pending"
DOCUMENT_INDEXING = "indexing"
DOCUMENT_READY = "ready"
DOCUMENT_FAILED = "failed"

TASK_PENDING = "pending"
TASK_RUNNING = "running"
TASK_SUCCEEDED = "succeeded"
TASK_FAILED = "failed"


@dataclass
class PolicyChunk:
    """Small document shape returned by company policy search."""

    page_content: str
    metadata: Dict[str, Any]


class DocumentRepository(Protocol):
    def create_document(self, record: Dict[str, Any]) -> Dict[str, Any]:
        ...

    def update_document(self, doc_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        ...

    def get_document(self, doc_id: str) -> Dict[str, Any]:
        ...

    def list_documents(self) -> List[Dict[str, Any]]:
        ...

    def create_task(self, record: Dict[str, Any]) -> Dict[str, Any]:
        ...

    def update_task(self, task_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        ...

    def get_task(self, task_id: str) -> Dict[str, Any]:
        ...


class DocumentNotFoundError(KeyError):
    """Raised when a document record cannot be found."""


class IndexingTaskNotFoundError(KeyError):
    """Raised when an indexing task record cannot be found."""


class JsonDocumentRepository:
    """Local JSON-backed document registry used as the dev fallback."""

    def __init__(self, registry_path: Path | str) -> None:
        self.registry_path = Path(registry_path)
        self.tasks_path = self.registry_path.with_name("indexing_tasks.json")

    def create_document(self, record: Dict[str, Any]) -> Dict[str, Any]:
        records = self._load_records()
        records.append(record)
        self._write_records(records)
        return self._normalize_document(record)

    def update_document(self, doc_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        records = self._load_records()
        for record in records:
            if record.get("doc_id") == doc_id:
                record.update(updates)
                self._write_records(records)
                return self._normalize_document(record)
        raise DocumentNotFoundError(doc_id)

    def get_document(self, doc_id: str) -> Dict[str, Any]:
        for record in self._load_records():
            if record.get("doc_id") == doc_id:
                return self._normalize_document(record)
        raise DocumentNotFoundError(doc_id)

    def list_documents(self) -> List[Dict[str, Any]]:
        return [self._normalize_document(record) for record in self._load_records()]

    def create_task(self, record: Dict[str, Any]) -> Dict[str, Any]:
        records = self._load_tasks()
        records.append(record)
        self._write_tasks(records)
        return dict(record)

    def update_task(self, task_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        records = self._load_tasks()
        for record in records:
            if record.get("task_id") == task_id:
                record.update(updates)
                self._write_tasks(records)
                return dict(record)
        raise IndexingTaskNotFoundError(task_id)

    def get_task(self, task_id: str) -> Dict[str, Any]:
        for record in self._load_tasks():
            if record.get("task_id") == task_id:
                return dict(record)
        raise IndexingTaskNotFoundError(task_id)

    def _load_records(self) -> List[Dict[str, Any]]:
        if not self.registry_path.exists():
            return []
        data = json.loads(self.registry_path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []

    def _write_records(self, records: List[Dict[str, Any]]) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_tasks(self) -> List[Dict[str, Any]]:
        if not self.tasks_path.exists():
            return []
        data = json.loads(self.tasks_path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []

    def _write_tasks(self, records: List[Dict[str, Any]]) -> None:
        self.tasks_path.parent.mkdir(parents=True, exist_ok=True)
        self.tasks_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _normalize_document(record: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(record)
        normalized.setdefault("chunk_count", 0)
        normalized.setdefault("status", DOCUMENT_READY)
        normalized.setdefault("error_message", None)
        normalized.setdefault("task_id", None)
        normalized.setdefault("indexed_at", None)
        normalized.setdefault("stored_path", None)
        return normalized


class PostgresDocumentRepository:
    """SQLAlchemy-backed document registry for production deployments."""

    def create_document(self, record: Dict[str, Any]) -> Dict[str, Any]:
        with session_scope() as session:
            model = DocumentModel(**record)
            session.add(model)
            session.flush()
            return self._document_to_dict(model)

    def update_document(self, doc_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        with session_scope() as session:
            model = session.get(DocumentModel, doc_id)
            if model is None:
                raise DocumentNotFoundError(doc_id)
            for key, value in updates.items():
                setattr(model, key, value)
            session.flush()
            return self._document_to_dict(model)

    def get_document(self, doc_id: str) -> Dict[str, Any]:
        with session_scope() as session:
            model = session.get(DocumentModel, doc_id)
            if model is None:
                raise DocumentNotFoundError(doc_id)
            return self._document_to_dict(model)

    def list_documents(self) -> List[Dict[str, Any]]:
        with session_scope() as session:
            models = session.scalars(
                select(DocumentModel).order_by(DocumentModel.created_at.desc())
            ).all()
            return [self._document_to_dict(model) for model in models]

    def create_task(self, record: Dict[str, Any]) -> Dict[str, Any]:
        with session_scope() as session:
            model = IndexingTaskModel(**record)
            session.add(model)
            session.flush()
            return self._task_to_dict(model)

    def update_task(self, task_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        with session_scope() as session:
            model = session.get(IndexingTaskModel, task_id)
            if model is None:
                raise IndexingTaskNotFoundError(task_id)
            for key, value in updates.items():
                setattr(model, key, value)
            session.flush()
            return self._task_to_dict(model)

    def get_task(self, task_id: str) -> Dict[str, Any]:
        with session_scope() as session:
            model = session.get(IndexingTaskModel, task_id)
            if model is None:
                raise IndexingTaskNotFoundError(task_id)
            return self._task_to_dict(model)

    @staticmethod
    def _document_to_dict(model: DocumentModel) -> Dict[str, Any]:
        return {
            "doc_id": model.doc_id,
            "file_name": model.file_name,
            "source_type": model.source_type,
            "chunk_count": model.chunk_count,
            "status": model.status,
            "error_message": model.error_message,
            "task_id": model.task_id,
            "stored_path": model.stored_path,
            "created_at": model.created_at,
            "indexed_at": model.indexed_at,
        }

    @staticmethod
    def _task_to_dict(model: IndexingTaskModel) -> Dict[str, Any]:
        return {
            "task_id": model.task_id,
            "doc_id": model.doc_id,
            "status": model.status,
            "attempts": model.attempts,
            "last_error": model.last_error,
            "created_at": model.created_at,
            "updated_at": model.updated_at,
        }


class DocumentService:
    """Manage enterprise documents in a dedicated LlamaIndex Chroma index."""

    SUPPORTED_TYPES = {"txt", "md", "pdf", "docx"}
    COMPANY_COLLECTION = "company_policy_docs"

    def __init__(
        self,
        uploads_dir: Path | str | None = None,
        registry_path: Path | str | None = None,
        persist_dir: Path | str | None = None,
        embedding_model: str | None = None,
        repository: DocumentRepository | None = None,
    ) -> None:
        self.uploads_dir = Path(uploads_dir or settings.uploads_dir)
        self.registry_path = Path(registry_path or settings.document_registry_path)
        self.persist_dir = Path(persist_dir or settings.llama_company_chroma_persist_dir)
        self.embedding_model = embedding_model or settings.embedding_model
        self.repository = repository or self._default_repository(registry_path)
        self._index: Any | None = None
        self._lock = Lock()

    def ingest_upload(self, file_name: str, content: bytes) -> Dict[str, Any]:
        """Synchronously save, parse, index, and register a document.

        This keeps local development and existing tests lightweight. Production
        API uploads use submit_upload so indexing can run in a worker.
        """

        source_type = self._detect_source_type(file_name)
        self._validate_upload(content)
        text = self._parse_content(source_type, content)
        doc_id = str(uuid4())
        safe_name = Path(file_name).name or f"{doc_id}.{source_type}"
        now = self._now()

        with self._lock:
            self._ensure_storage()
            saved_path = self.uploads_dir / f"{doc_id}_{safe_name}"
            saved_path.write_bytes(content)

            chunks = self._build_chunks(doc_id, safe_name, source_type, text)
            self._index_chunks(chunks)

            record = {
                "doc_id": doc_id,
                "file_name": safe_name,
                "source_type": source_type,
                "chunk_count": len(chunks),
                "status": DOCUMENT_READY,
                "error_message": None,
                "task_id": None,
                "stored_path": str(saved_path),
                "created_at": now,
                "indexed_at": now,
            }
            return self.repository.create_document(record)

    def submit_upload(self, file_name: str, content: bytes) -> Dict[str, Any]:
        """Create a document record and enqueue indexing when Redis is configured."""

        source_type = self._detect_source_type(file_name)
        self._validate_upload(content)
        doc_id = str(uuid4())
        task_id = str(uuid4())
        safe_name = Path(file_name).name or f"{doc_id}.{source_type}"
        now = self._now()

        with self._lock:
            self._ensure_storage()
            saved_path = self.uploads_dir / f"{doc_id}_{safe_name}"
            saved_path.write_bytes(content)
            record = self.repository.create_document(
                {
                    "doc_id": doc_id,
                    "file_name": safe_name,
                    "source_type": source_type,
                    "chunk_count": 0,
                    "status": DOCUMENT_PENDING,
                    "error_message": None,
                    "task_id": task_id,
                    "stored_path": str(saved_path),
                    "created_at": now,
                    "indexed_at": None,
                }
            )
            self.repository.create_task(
                {
                    "task_id": task_id,
                    "doc_id": doc_id,
                    "status": TASK_PENDING,
                    "attempts": 0,
                    "last_error": None,
                    "created_at": now,
                    "updated_at": now,
                }
            )

        queue = create_indexing_queue()
        if queue is None:
            return self.process_indexing_task(task_id)
        queue.enqueue(IndexingMessage(task_id=task_id, doc_id=doc_id))
        return record

    def process_indexing_task(self, task_id: str) -> Dict[str, Any]:
        task = self.repository.get_task(task_id)
        doc_id = task["doc_id"]
        attempts = int(task.get("attempts") or 0) + 1
        now = self._now()
        self.repository.update_task(
            task_id,
            {"status": TASK_RUNNING, "attempts": attempts, "updated_at": now},
        )
        self.repository.update_document(
            doc_id,
            {"status": DOCUMENT_INDEXING, "error_message": None},
        )

        try:
            document = self.repository.get_document(doc_id)
            source_type = str(document["source_type"])
            saved_path = Path(str(document.get("stored_path") or ""))
            if not saved_path.exists():
                raise FileNotFoundError(f"Uploaded file not found: {saved_path}")
            content = saved_path.read_bytes()
            text = self._parse_content(source_type, content)
            chunks = self._build_chunks(
                doc_id,
                str(document["file_name"]),
                source_type,
                text,
            )
            self._index_chunks(chunks)
            indexed_at = self._now()
            self.repository.update_task(
                task_id,
                {
                    "status": TASK_SUCCEEDED,
                    "last_error": None,
                    "updated_at": indexed_at,
                },
            )
            return self.repository.update_document(
                doc_id,
                {
                    "chunk_count": len(chunks),
                    "status": DOCUMENT_READY,
                    "error_message": None,
                    "indexed_at": indexed_at,
                },
            )
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            failed_at = self._now()
            self.repository.update_task(
                task_id,
                {
                    "status": TASK_FAILED,
                    "last_error": message,
                    "updated_at": failed_at,
                },
            )
            self.repository.update_document(
                doc_id,
                {
                    "status": DOCUMENT_FAILED,
                    "error_message": message,
                    "indexed_at": None,
                },
            )
            raise

    def list_documents(self) -> List[Dict[str, Any]]:
        with self._lock:
            return self.repository.list_documents()

    def status_counts(self) -> Dict[str, int]:
        counts = {
            DOCUMENT_PENDING: 0,
            DOCUMENT_INDEXING: 0,
            DOCUMENT_READY: 0,
            DOCUMENT_FAILED: 0,
        }
        for record in self.list_documents():
            status = str(record.get("status") or DOCUMENT_READY)
            counts[status] = counts.get(status, 0) + 1
        counts["total"] = sum(counts.values())
        return counts

    def search(self, query: str, k: int = 4) -> List[PolicyChunk]:
        if not settings.chroma_host and (
            not self.persist_dir.exists() or not any(self.persist_dir.iterdir())
        ):
            return []
        if self.status_counts().get(DOCUMENT_READY, 0) == 0:
            return []
        index = self._get_vectorstore()
        if hasattr(index, "similarity_search"):
            return index.similarity_search(query, k=k)
        retriever = index.as_retriever(similarity_top_k=k)
        return [self._chunk_from_node(item) for item in retriever.retrieve(query)]

    @classmethod
    def _detect_source_type(cls, file_name: str) -> str:
        source_type = Path(file_name).suffix.lower().lstrip(".")
        if source_type not in cls.SUPPORTED_TYPES:
            raise NotImplementedError(f"Unsupported document type: {source_type or 'unknown'}")
        return source_type

    def _validate_upload(self, content: bytes) -> None:
        if not content:
            raise ValueError("Uploaded document is empty")
        max_bytes = settings.max_upload_mb * 1024 * 1024
        if len(content) > max_bytes:
            raise ValueError(f"Uploaded document exceeds {settings.max_upload_mb}MB")

    def _parse_content(self, source_type: str, content: bytes) -> str:
        if source_type in {"txt", "md"}:
            return content.decode("utf-8-sig")
        if source_type == "pdf":
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(content))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        if source_type == "docx":
            from docx import Document as DocxDocument

            document = DocxDocument(BytesIO(content))
            return "\n".join(paragraph.text for paragraph in document.paragraphs)
        raise NotImplementedError(f"Unsupported document type: {source_type}")

    def _build_chunks(
        self,
        doc_id: str,
        file_name: str,
        source_type: str,
        text: str,
    ) -> List[PolicyChunk]:
        return [
            PolicyChunk(
                page_content=chunk,
                metadata={
                    "doc_id": doc_id,
                    "file_name": file_name,
                    "source_type": source_type,
                    "chunk_id": chunk_id,
                },
            )
            for chunk_id, chunk in enumerate(self._split_text(text))
        ]

    def _split_text(
        self,
        text: str,
        chunk_size: int = 1500,
        chunk_overlap: int = 300,
    ) -> List[str]:
        cleaned = text.strip()
        if not cleaned:
            return []

        chunks: List[str] = []
        start = 0
        while start < len(cleaned):
            end = min(start + chunk_size, len(cleaned))
            chunks.append(cleaned[start:end])
            if end == len(cleaned):
                break
            start = max(end - chunk_overlap, start + 1)
        return chunks

    def _index_chunks(self, chunks: Iterable[PolicyChunk]) -> None:
        chunk_list = list(chunks)
        if not chunk_list:
            return
        index = self._get_vectorstore()
        if hasattr(index, "add_documents"):
            index.add_documents(chunk_list)
            return
        index.insert_nodes([self._node_from_chunk(chunk) for chunk in chunk_list])

    def _get_vectorstore(self) -> Any:
        if self._index is None:
            from llama_index.core import Settings, StorageContext, VectorStoreIndex
            from llama_index.embeddings.huggingface import HuggingFaceEmbedding
            from llama_index.vector_stores.chroma import ChromaVectorStore
            from app.rag.chroma_client import create_chroma_client

            Settings.embed_model = HuggingFaceEmbedding(model_name=self.embedding_model)
            self.persist_dir.mkdir(parents=True, exist_ok=True)
            client = create_chroma_client(self.persist_dir)
            collection = client.get_or_create_collection(self.COMPANY_COLLECTION)
            vector_store = ChromaVectorStore(chroma_collection=collection)
            storage_context = StorageContext.from_defaults(vector_store=vector_store)
            if collection.count() == 0:
                self._index = VectorStoreIndex([], storage_context=storage_context)
            else:
                self._index = VectorStoreIndex.from_vector_store(
                    vector_store=vector_store,
                    storage_context=storage_context,
                )
        return self._index

    def _node_from_chunk(self, chunk: PolicyChunk) -> Any:
        try:
            from llama_index.core.schema import TextNode

            return TextNode(text=chunk.page_content, metadata=chunk.metadata)
        except ImportError:
            return chunk

    def _chunk_from_node(self, item: Any) -> PolicyChunk:
        node = getattr(item, "node", item)
        metadata = dict(getattr(node, "metadata", {}) or {})
        if hasattr(node, "get_content"):
            text = str(node.get_content())
        else:
            text = str(getattr(node, "text", getattr(node, "page_content", "")))
        return PolicyChunk(page_content=text, metadata=metadata)

    def _ensure_storage(self) -> None:
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.persist_dir.mkdir(parents=True, exist_ok=True)

    def _load_registry(self) -> List[Dict[str, Any]]:
        if isinstance(self.repository, JsonDocumentRepository):
            return self.repository.list_documents()
        return self.repository.list_documents()

    def _write_registry(self, records: List[Dict[str, Any]]) -> None:
        if not isinstance(self.repository, JsonDocumentRepository):
            raise RuntimeError("Direct registry writes are only supported by JSON fallback")
        self.repository._write_records(records)

    def _default_repository(self, registry_path: Path | str | None) -> DocumentRepository:
        if settings.database_url and registry_path is None:
            return PostgresDocumentRepository()
        return JsonDocumentRepository(self.registry_path)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()


document_service = DocumentService()
