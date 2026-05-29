"""Database models and session helpers for production persistence."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import JSON, Column, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


class DocumentModel(Base):
    __tablename__ = "documents"

    doc_id = Column(String(64), primary_key=True)
    file_name = Column(String(512), nullable=False)
    source_type = Column(String(32), nullable=False)
    chunk_count = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default="pending")
    error_message = Column(Text, nullable=True)
    task_id = Column(String(64), nullable=True, index=True)
    stored_path = Column(Text, nullable=True)
    created_at = Column(String(64), nullable=False)
    indexed_at = Column(String(64), nullable=True)


class ReviewRecordModel(Base):
    __tablename__ = "review_records"

    review_id = Column(String(64), primary_key=True)
    source_type = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, index=True)
    payload = Column(JSON, nullable=False, default=dict)
    final_answer = Column(JSON, nullable=True)
    created_at = Column(String(64), nullable=False)
    updated_at = Column(String(64), nullable=False)


class IndexingTaskModel(Base):
    __tablename__ = "indexing_tasks"

    task_id = Column(String(64), primary_key=True)
    doc_id = Column(String(64), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(String(64), nullable=False)
    updated_at = Column(String(64), nullable=False)


def _engine_kwargs(database_url: str) -> dict:
    kwargs = {"pool_pre_ping": True, "future": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return kwargs


engine = (
    create_engine(settings.database_url, **_engine_kwargs(settings.database_url))
    if settings.database_url
    else None
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True) if engine else None


def init_database() -> None:
    """Create tables for the lightweight demo deployment.

    Alembic migrations are included for production discipline; this helper keeps
    one-command demo deployments from failing when migrations have not run yet.
    """

    if engine is not None:
        Base.metadata.create_all(bind=engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
