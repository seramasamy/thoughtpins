"""grant privileges to non-owner app database role

Revision ID: 0009_postgres_app_role_grants
Revises: 0008_chat_durability
Create Date: 2026-07-01
"""

from __future__ import annotations

import os
import re

import sqlalchemy as sa

from alembic import op

revision = "0009_postgres_app_role_grants"
down_revision = "0008_chat_durability"
branch_labels = None
depends_on = None

APP_ROLE_ENV = "THOUGHTPINS_APP_DB_ROLE"


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _app_role() -> str:
    role = os.getenv(APP_ROLE_ENV, "").strip()
    if not role:
        return ""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", role):
        raise ValueError(f"{APP_ROLE_ENV} must be a simple PostgreSQL role name")
    return role


def _role_exists(role: str) -> bool:
    bind = op.get_bind()
    return bool(bind.execute(sa.text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": role}).scalar())


def _q(role: str) -> str:
    return f'"{role}"'


def upgrade() -> None:
    if not _is_postgres():
        return

    role = _app_role()
    if not role or not _role_exists(role):
        return

    quoted = _q(role)
    op.execute(f"GRANT USAGE ON SCHEMA public TO {quoted}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {quoted}")
    op.execute(f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO {quoted}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {quoted}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {quoted}")


def downgrade() -> None:
    if not _is_postgres():
        return

    role = _app_role()
    if not role or not _role_exists(role):
        return

    quoted = _q(role)
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT, UPDATE ON SEQUENCES FROM {quoted}")
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {quoted}"
    )
    op.execute(f"REVOKE USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public FROM {quoted}")
    op.execute(f"REVOKE SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public FROM {quoted}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {quoted}")
