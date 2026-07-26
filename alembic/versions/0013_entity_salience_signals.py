"""persist explainable entity salience signals

Revision ID: 0013_entity_salience_signals
Revises: 0012_contextual_salience
Create Date: 2026-07-12
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0013_entity_salience_signals"
down_revision = "0012_contextual_salience"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    if "salience_signals_json" not in _columns("entities"):
        with op.batch_alter_table("entities") as batch:
            batch.add_column(sa.Column("salience_signals_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    if "salience_signals_json" in _columns("entities"):
        with op.batch_alter_table("entities") as batch:
            batch.drop_column("salience_signals_json")
