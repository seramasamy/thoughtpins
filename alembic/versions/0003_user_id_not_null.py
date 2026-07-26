"""enforce non-null tenant ownership

Revision ID: 0003_user_id_not_null
Revises: 0002_postgres_rls_policies
Create Date: 2026-05-22
"""

from alembic import op

revision = "0003_user_id_not_null"
down_revision = "0002_postgres_rls_policies"
branch_labels = None
depends_on = None

USER_OWNED_TABLES = [
    "auth_sessions",
    "ingestion_jobs",
    "raw_entries",
    "entities",
    "entity_mentions",
    "memories",
    "relationships",
    "events",
    "event_participants",
    "action_items",
    "expenses",
    "reports",
]


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return
    for table in USER_OWNED_TABLES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN user_id SET NOT NULL")


def downgrade() -> None:
    if not _is_postgres():
        return
    for table in USER_OWNED_TABLES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN user_id DROP NOT NULL")
