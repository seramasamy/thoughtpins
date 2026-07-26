"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-22
"""

from alembic import op
from thoughtpins.migrations.frozen_initial_schema import build_initial_metadata

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    build_initial_metadata().create_all(bind=op.get_bind())


def downgrade() -> None:
    build_initial_metadata().drop_all(bind=op.get_bind())
