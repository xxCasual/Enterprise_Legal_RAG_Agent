"""create production persistence tables

Revision ID: 20260528_0001
Revises:
Create Date: 2026-05-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260528_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("doc_id", sa.String(length=64), primary_key=True),
        sa.Column("file_name", sa.String(length=512), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("task_id", sa.String(length=64), nullable=True),
        sa.Column("stored_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("indexed_at", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_documents_task_id", "documents", ["task_id"])

    op.create_table(
        "review_records",
        sa.Column("review_id", sa.String(length=64), primary_key=True),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("final_answer", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_review_records_status", "review_records", ["status"])

    op.create_table(
        "indexing_tasks",
        sa.Column("task_id", sa.String(length=64), primary_key=True),
        sa.Column("doc_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_indexing_tasks_doc_id", "indexing_tasks", ["doc_id"])
    op.create_index("ix_indexing_tasks_status", "indexing_tasks", ["status"])


def downgrade() -> None:
    op.drop_index("ix_indexing_tasks_status", table_name="indexing_tasks")
    op.drop_index("ix_indexing_tasks_doc_id", table_name="indexing_tasks")
    op.drop_table("indexing_tasks")
    op.drop_index("ix_review_records_status", table_name="review_records")
    op.drop_table("review_records")
    op.drop_index("ix_documents_task_id", table_name="documents")
    op.drop_table("documents")
