"""Let a chat turn be edited and resent without losing what it wrote.

Editing a message in a chat product discards the branch below it. In a
journaling product that branch may have written durable memory — a raw entry,
extracted memories, a saved source — so the superseded turn is marked rather
than deleted. The record of what was said stays; it just stops being part of
the live conversation.

Revision ID: 0026_chat_message_supersede
Revises: 0025_operator_notifications
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0026_chat_message_supersede"
down_revision = "0025_operator_notifications"
branch_labels = None
depends_on = None


TABLE = "chat_messages"
LIVE_INDEX = "ix_chat_messages_user_conversation_live"


def upgrade() -> None:
    # Guarded because a local database may have been created by create_all at a
    # newer model revision and then stamped, so these may already exist. The
    # migration round-trip check exercises exactly that path.
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns(TABLE)}
    if "superseded_at_utc" not in columns:
        op.add_column(TABLE, sa.Column("superseded_at_utc", sa.DateTime(), nullable=True))
    if "superseded_by_message_id" not in columns:
        op.add_column(TABLE, sa.Column("superseded_by_message_id", sa.String(length=32), nullable=True))

    # Replaying a conversation asks for the live turns of one user in order, so
    # the supersede flag belongs in the index that lookup already uses.
    if LIVE_INDEX not in {index["name"] for index in inspector.get_indexes(TABLE)}:
        op.create_index(
            LIVE_INDEX,
            TABLE,
            ["user_id", "conversation_id", "superseded_at_utc", "created_at_utc"],
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if LIVE_INDEX in {index["name"] for index in inspector.get_indexes(TABLE)}:
        op.drop_index(LIVE_INDEX, table_name=TABLE)
    columns = {column["name"] for column in inspector.get_columns(TABLE)}
    if "superseded_by_message_id" in columns:
        op.drop_column(TABLE, "superseded_by_message_id")
    if "superseded_at_utc" in columns:
        op.drop_column(TABLE, "superseded_at_utc")
