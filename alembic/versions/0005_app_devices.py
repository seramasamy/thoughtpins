"""add app device registrations

Revision ID: 0005_app_devices
Revises: 0004_audit_log_rls
Create Date: 2026-05-23
"""

import sqlalchemy as sa

from alembic import op

revision = "0005_app_devices"
down_revision = "0004_audit_log_rls"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return name in inspector.get_table_names()


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _has_table("app_devices"):
        op.create_table(
            "app_devices",
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column("user_id", sa.String(length=32), nullable=False),
            sa.Column("installation_id", sa.String(length=128), nullable=False),
            sa.Column("platform", sa.String(length=16), nullable=False),
            sa.Column("device_name", sa.String(length=128), nullable=True),
            sa.Column("app_version", sa.String(length=32), nullable=True),
            sa.Column("build_number", sa.String(length=32), nullable=True),
            sa.Column("os_version", sa.String(length=64), nullable=True),
            sa.Column("locale", sa.String(length=32), nullable=True),
            sa.Column("timezone", sa.String(length=64), nullable=True),
            sa.Column("push_provider", sa.String(length=16), nullable=True),
            sa.Column("push_token_hash", sa.String(length=128), nullable=True),
            sa.Column("push_token_encrypted", sa.Text(), nullable=True),
            sa.Column("notifications_enabled", sa.Boolean(), nullable=True),
            sa.Column("created_at_utc", sa.DateTime(), nullable=True),
            sa.Column("last_seen_at_utc", sa.DateTime(), nullable=True),
            sa.Column("revoked_at_utc", sa.DateTime(), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_app_devices_user_id", "app_devices", ["user_id"])
        op.create_index("ix_app_devices_push_token_hash", "app_devices", ["push_token_hash"])
        op.create_index("ix_app_devices_created_at_utc", "app_devices", ["created_at_utc"])
        op.create_index("ix_app_devices_last_seen_at_utc", "app_devices", ["last_seen_at_utc"])
        op.create_index("ix_app_devices_revoked_at_utc", "app_devices", ["revoked_at_utc"])
        op.create_index(
            "ix_app_devices_user_installation",
            "app_devices",
            ["user_id", "installation_id"],
            unique=True,
        )
        op.create_index("ix_app_devices_user_platform", "app_devices", ["user_id", "platform"])

    if _is_postgres():
        tenant_expr = "NULLIF(current_setting('app.current_user_id', true), '')"
        op.execute("ALTER TABLE app_devices ENABLE ROW LEVEL SECURITY")
        op.execute("DROP POLICY IF EXISTS thoughtpins_tenant_isolation ON app_devices")
        op.execute(
            f"""
            CREATE POLICY thoughtpins_tenant_isolation ON app_devices
            USING (user_id = {tenant_expr})
            WITH CHECK (user_id = {tenant_expr})
            """
        )


def downgrade() -> None:
    if _is_postgres():
        op.execute("DROP POLICY IF EXISTS thoughtpins_tenant_isolation ON app_devices")
        op.execute("ALTER TABLE app_devices DISABLE ROW LEVEL SECURITY")
    if _has_table("app_devices"):
        op.drop_table("app_devices")
