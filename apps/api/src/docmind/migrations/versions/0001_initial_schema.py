"""Initial schema: users, workspaces, documents, chunks, conversations, caches, usage, audit.

Revision ID: 0001
Revises:
Create Date: 2026-10-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

from docmind.core.config import get_settings
from docmind.db.types import Embedding

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = pg.UUID(as_uuid=True)
TS = sa.DateTime(timezone=True)


def _id() -> sa.Column[object]:
    return sa.Column("id", UUID, nullable=False)


def _created() -> sa.Column[object]:
    return sa.Column("created_at", TS, nullable=False, server_default=sa.func.now())


def _updated() -> sa.Column[object]:
    return sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now())


def _fk(column: str, table: str, ondelete: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint([column], [f"{table}.id"], ondelete=ondelete)


def upgrade() -> None:
    # The embedding width is fixed per deployment (EMBEDDING_DIM, 384 for bge-small).
    # Changing models later means a new migration and `docmind reindex`.
    dim = get_settings().embedding_dim
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "users",
        _id(),
        sa.Column("email", pg.CITEXT(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("session_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("failed_logins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", TS),
        sa.Column("last_login_at", TS),
        _created(),
        _updated(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "workspaces",
        _id(),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("settings", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("corpus_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", UUID),
        _created(),
        _updated(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
        _fk("created_by", "users", "SET NULL"),
    )

    op.create_table(
        "memberships",
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        _created(),
        sa.PrimaryKeyConstraint("workspace_id", "user_id"),
        _fk("workspace_id", "workspaces", "CASCADE"),
        _fk("user_id", "users", "CASCADE"),
        sa.CheckConstraint("role IN ('owner', 'editor', 'viewer')", name="role"),
    )
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])

    op.create_table(
        "api_keys",
        _id(),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("created_by", UUID),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("prefix", sa.String(16), nullable=False),
        sa.Column("secret_hash", sa.String(64), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("last_used_at", TS),
        sa.Column("expires_at", TS),
        sa.Column("revoked_at", TS),
        _created(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prefix"),
        _fk("workspace_id", "workspaces", "CASCADE"),
        _fk("created_by", "users", "SET NULL"),
        sa.CheckConstraint("role IN ('editor', 'viewer')", name="role"),
    )
    op.create_index("ix_api_keys_workspace_id", "api_keys", ["workspace_id"])

    op.create_table(
        "documents",
        _id(),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("filename", sa.String(300), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("mime_type", sa.String(160), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(400), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("warnings", pg.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("section_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("uploaded_by", UUID),
        sa.Column("processed_at", TS),
        _created(),
        _updated(),
        sa.PrimaryKeyConstraint("id"),
        # The same bytes uploaded twice to one workspace are one document.
        sa.UniqueConstraint("workspace_id", "sha256"),
        _fk("workspace_id", "workspaces", "CASCADE"),
        _fk("uploaded_by", "users", "SET NULL"),
        sa.CheckConstraint("status IN ('queued', 'processing', 'ready', 'failed')", name="status"),
        sa.CheckConstraint(
            "kind IN ('pdf', 'docx', 'xlsx', 'csv', 'pptx', 'txt', 'md', 'html')", name="kind"
        ),
    )
    op.create_index(
        "ix_documents_workspace_id_created_at", "documents", ["workspace_id", "created_at"]
    )
    # Small partial index for the stale-job reaper: only unfinished documents are in it.
    op.create_index(
        "ix_documents_unfinished",
        "documents",
        ["updated_at"],
        postgresql_where=sa.text("status IN ('queued', 'processing')"),
    )

    op.create_table(
        "document_sections",
        _id(),
        sa.Column("document_id", UUID, nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("label", sa.String(300), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "ordinal"),
        _fk("document_id", "documents", "CASCADE"),
        sa.CheckConstraint("kind IN ('page', 'slide', 'sheet', 'section')", name="kind"),
    )

    op.create_table(
        "chunks",
        _id(),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("document_id", UUID, nullable=False),
        sa.Column("section_ordinal", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("heading", sa.Text(), nullable=False, server_default=""),
        sa.Column("location", sa.String(300), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("embedding", Embedding(dim), nullable=False),
        sa.Column(
            "tsv",
            pg.TSVECTOR(),
            sa.Computed(
                "to_tsvector('english', coalesce(heading, '') || ' ' || text)", persisted=True
            ),
        ),
        sa.PrimaryKeyConstraint("id"),
        _fk("workspace_id", "workspaces", "CASCADE"),
        _fk("document_id", "documents", "CASCADE"),
    )
    op.create_index("ix_chunks_workspace_id", "chunks", ["workspace_id"])
    op.create_index("ix_chunks_document_id_ordinal", "chunks", ["document_id", "ordinal"])
    op.create_index("ix_chunks_tsv", "chunks", ["tsv"], postgresql_using="gin")
    op.create_index(
        "ix_chunks_embedding_hnsw",
        "chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "conversations",
        _id(),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("document_ids", pg.ARRAY(UUID)),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        _created(),
        _updated(),
        sa.PrimaryKeyConstraint("id"),
        _fk("workspace_id", "workspaces", "CASCADE"),
        _fk("user_id", "users", "CASCADE"),
    )
    op.create_index(
        "ix_conversations_workspace_id_user_id_updated_at",
        "conversations",
        ["workspace_id", "user_id", "updated_at"],
    )

    op.create_table(
        "messages",
        _id(),
        sa.Column("conversation_id", UUID, nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", pg.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("sources", pg.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("usage", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        _created(),
        sa.PrimaryKeyConstraint("id"),
        _fk("conversation_id", "conversations", "CASCADE"),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="role"),
    )
    op.create_index(
        "ix_messages_conversation_id_created_at", "messages", ["conversation_id", "created_at"]
    )

    op.create_table(
        "usage_events",
        _id(),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("user_id", UUID),
        sa.Column("api_key_id", UUID),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("cache", sa.String(16), nullable=False),
        sa.Column("generator", sa.String(120), nullable=False),
        sa.Column("context_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("baseline_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("saved_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "cited_document_ids",
            pg.ARRAY(UUID),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        _created(),
        sa.PrimaryKeyConstraint("id"),
        _fk("workspace_id", "workspaces", "CASCADE"),
        _fk("user_id", "users", "SET NULL"),
        _fk("api_key_id", "api_keys", "SET NULL"),
        sa.CheckConstraint("kind IN ('answer', 'search')", name="kind"),
        sa.CheckConstraint("cache IN ('miss', 'exact', 'semantic')", name="cache"),
    )
    op.create_index(
        "ix_usage_events_workspace_id_created_at", "usage_events", ["workspace_id", "created_at"]
    )

    op.create_table(
        "answer_cache",
        _id(),
        sa.Column("workspace_id", UUID, nullable=False),
        sa.Column("scope_hash", sa.String(64), nullable=False),
        sa.Column("corpus_version", sa.Integer(), nullable=False),
        sa.Column("generator", sa.String(120), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("question_embedding", Embedding(dim), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("citations", pg.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("usage", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("hits", sa.Integer(), nullable=False, server_default="0"),
        _created(),
        sa.Column("last_hit_at", TS),
        sa.Column("expires_at", TS, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        _fk("workspace_id", "workspaces", "CASCADE"),
    )
    op.create_index(
        "ix_answer_cache_lookup",
        "answer_cache",
        ["workspace_id", "scope_hash", "corpus_version", "generator"],
    )
    op.create_index("ix_answer_cache_expires_at", "answer_cache", ["expires_at"])

    op.create_table(
        "audit_events",
        _id(),
        sa.Column("workspace_id", UUID),
        sa.Column("actor_user_id", UUID),
        sa.Column("actor_api_key_id", UUID),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(64)),
        sa.Column("details", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        _created(),
        sa.PrimaryKeyConstraint("id"),
        _fk("workspace_id", "workspaces", "CASCADE"),
        _fk("actor_user_id", "users", "SET NULL"),
        _fk("actor_api_key_id", "api_keys", "SET NULL"),
    )
    op.create_index(
        "ix_audit_events_workspace_id_created_at", "audit_events", ["workspace_id", "created_at"]
    )


def downgrade() -> None:
    for table in (
        "audit_events",
        "answer_cache",
        "usage_events",
        "messages",
        "conversations",
        "chunks",
        "document_sections",
        "documents",
        "api_keys",
        "memberships",
        "workspaces",
        "users",
    ):
        op.drop_table(table)
