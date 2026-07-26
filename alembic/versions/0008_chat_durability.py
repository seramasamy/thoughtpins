"""add durable chat conversations and pending actions

Revision ID: 0008_chat_durability
Revises: 0007_article_provenance_fields
Create Date: 2026-06-01
"""

import sqlalchemy as sa

from alembic import op

revision = "0008_chat_durability"
down_revision = "0007_article_provenance_fields"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return name in inspector.get_table_names()


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _enable_rls(table_name: str) -> None:
    tenant_expr = "NULLIF(current_setting('app.current_user_id', true), '')"
    op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS thoughtpins_tenant_isolation ON {table_name}")
    op.execute(
        f"""
        CREATE POLICY thoughtpins_tenant_isolation ON {table_name}
        USING (user_id = {tenant_expr})
        WITH CHECK (user_id = {tenant_expr})
        """
    )


def upgrade() -> None:
    if not _has_table("chat_conversations"):
        op.create_table(
            "chat_conversations",
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column("user_id", sa.String(length=32), nullable=False),
            sa.Column("conversation_key", sa.String(length=128), nullable=False),
            sa.Column("surface", sa.String(length=32), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=True),
            sa.Column("created_at_utc", sa.DateTime(), nullable=True),
            sa.Column("updated_at_utc", sa.DateTime(), nullable=True),
            sa.Column("last_message_at_utc", sa.DateTime(), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_chat_conversations_user_id", "chat_conversations", ["user_id"])
        op.create_index("ix_chat_conversations_created_at_utc", "chat_conversations", ["created_at_utc"])
        op.create_index("ix_chat_conversations_updated_at_utc", "chat_conversations", ["updated_at_utc"])
        op.create_index("ix_chat_conversations_last_message_at_utc", "chat_conversations", ["last_message_at_utc"])
        op.create_index(
            "ix_chat_conversations_user_key",
            "chat_conversations",
            ["user_id", "conversation_key"],
            unique=True,
        )
        op.create_index(
            "ix_chat_conversations_user_updated",
            "chat_conversations",
            ["user_id", "updated_at_utc"],
        )

    if not _has_table("chat_messages"):
        op.create_table(
            "chat_messages",
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column("user_id", sa.String(length=32), nullable=False),
            sa.Column("conversation_id", sa.String(length=32), nullable=False),
            sa.Column("role", sa.String(length=16), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("route_type", sa.String(length=64), nullable=True),
            sa.Column("status", sa.String(length=64), nullable=True),
            sa.Column("raw_entry_id", sa.String(length=32), nullable=True),
            sa.Column("job_id", sa.String(length=32), nullable=True),
            sa.Column("document_id", sa.String(length=32), nullable=True),
            sa.Column("created_at_utc", sa.DateTime(), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.ForeignKeyConstraint(["conversation_id"], ["chat_conversations.id"]),
            sa.ForeignKeyConstraint(["document_id"], ["document_sources.id"]),
            sa.ForeignKeyConstraint(["job_id"], ["ingestion_jobs.id"]),
            sa.ForeignKeyConstraint(["raw_entry_id"], ["raw_entries.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_chat_messages_user_id", "chat_messages", ["user_id"])
        op.create_index("ix_chat_messages_conversation_id", "chat_messages", ["conversation_id"])
        op.create_index("ix_chat_messages_raw_entry_id", "chat_messages", ["raw_entry_id"])
        op.create_index("ix_chat_messages_job_id", "chat_messages", ["job_id"])
        op.create_index("ix_chat_messages_document_id", "chat_messages", ["document_id"])
        op.create_index("ix_chat_messages_created_at_utc", "chat_messages", ["created_at_utc"])
        op.create_index(
            "ix_chat_messages_user_conversation_created",
            "chat_messages",
            ["user_id", "conversation_id", "created_at_utc"],
        )
        op.create_index("ix_chat_messages_user_role", "chat_messages", ["user_id", "role"])

    if not _has_table("pending_chat_actions"):
        op.create_table(
            "pending_chat_actions",
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column("user_id", sa.String(length=32), nullable=False),
            sa.Column("conversation_id", sa.String(length=32), nullable=False),
            sa.Column("action", sa.String(length=64), nullable=False),
            sa.Column("args_json", sa.JSON(), nullable=True),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("created_at_utc", sa.DateTime(), nullable=True),
            sa.Column("expires_at_utc", sa.DateTime(), nullable=False),
            sa.Column("resolved_at_utc", sa.DateTime(), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.ForeignKeyConstraint(["conversation_id"], ["chat_conversations.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_pending_chat_actions_user_id", "pending_chat_actions", ["user_id"])
        op.create_index("ix_pending_chat_actions_conversation_id", "pending_chat_actions", ["conversation_id"])
        op.create_index("ix_pending_chat_actions_status", "pending_chat_actions", ["status"])
        op.create_index("ix_pending_chat_actions_created_at_utc", "pending_chat_actions", ["created_at_utc"])
        op.create_index("ix_pending_chat_actions_expires_at_utc", "pending_chat_actions", ["expires_at_utc"])
        op.create_index(
            "ix_pending_chat_actions_user_status_expires",
            "pending_chat_actions",
            ["user_id", "status", "expires_at_utc"],
        )
        op.create_index(
            "ix_pending_chat_actions_user_conversation",
            "pending_chat_actions",
            ["user_id", "conversation_id"],
        )

    if _is_postgres():
        _enable_rls("chat_conversations")
        _enable_rls("chat_messages")
        _enable_rls("pending_chat_actions")


def downgrade() -> None:
    if _is_postgres():
        for table_name in ("pending_chat_actions", "chat_messages", "chat_conversations"):
            op.execute(f"DROP POLICY IF EXISTS thoughtpins_tenant_isolation ON {table_name}")
            op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")
    if _has_table("pending_chat_actions"):
        op.drop_table("pending_chat_actions")
    if _has_table("chat_messages"):
        op.drop_table("chat_messages")
    if _has_table("chat_conversations"):
        op.drop_table("chat_conversations")
