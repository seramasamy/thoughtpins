"""Exercise the complete Alembic chain against a disposable SQLite database."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import uuid4

from alembic.config import Config as AlembicConfig
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from alembic import command

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from thoughtpins.config import config
from thoughtpins.db import Base


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true", help="Keep the disposable database for inspection")
    args = parser.parse_args()

    scratch = (ROOT / ".tmp" / f"migration-roundtrip-{uuid4().hex}.sqlite3").resolve()
    legacy_scratch = (ROOT / ".tmp" / f"migration-legacy-local-{uuid4().hex}.sqlite3").resolve()
    scratch.parent.mkdir(parents=True, exist_ok=True)
    if ROOT not in scratch.parents:
        raise RuntimeError("Migration scratch path escaped the repository")
    database_url = f"sqlite:///{scratch.as_posix()}"
    config_class = type(config)
    original_url = config_class.DATABASE_URL
    config_class.DATABASE_URL = database_url
    alembic = AlembicConfig(str(ROOT / "alembic.ini"))
    alembic.set_main_option("script_location", str(ROOT / "alembic"))

    try:
        command.upgrade(alembic, "0001_initial_schema")
        _assert_initial_schema(database_url)
        command.upgrade(alembic, "head")
        _assert_head(alembic, database_url)
        _assert_schema(database_url, expect_retry_tables=True)

        command.downgrade(alembic, "0013_entity_salience_signals")
        _assert_schema(database_url, expect_retry_tables=False)

        command.upgrade(alembic, "head")
        _assert_head(alembic, database_url)
        _assert_schema(database_url, expect_retry_tables=True)

        legacy_url = f"sqlite:///{legacy_scratch.as_posix()}"
        legacy_engine = create_engine(legacy_url)
        try:
            Base.metadata.create_all(legacy_engine)
        finally:
            legacy_engine.dispose()
        config_class.DATABASE_URL = legacy_url
        command.stamp(alembic, "0015_ingestion_job_dedup")
        command.upgrade(alembic, "head")
        _assert_head(alembic, legacy_url)
        _assert_schema(legacy_url, expect_retry_tables=True)

        print("Migration round-trip check passed: empty -> head -> 0013 -> head; legacy local -> head")
        return 0
    finally:
        config_class.DATABASE_URL = original_url
        if not args.keep:
            scratch.unlink(missing_ok=True)
            legacy_scratch.unlink(missing_ok=True)


def _assert_head(alembic: AlembicConfig, database_url: str) -> None:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            current = MigrationContext.configure(connection).get_current_revision()
        expected = ScriptDirectory.from_config(alembic).get_current_head()
        if current != expected:
            raise RuntimeError(f"Migration head mismatch: database={current}, scripts={expected}")
    finally:
        engine.dispose()


def _assert_schema(database_url: str, *, expect_retry_tables: bool) -> None:
    engine = create_engine(database_url)
    try:
        schema = inspect(engine)
        tables = set(schema.get_table_names())
        if expect_retry_tables:
            missing = set(Base.metadata.tables) - tables
            if missing:
                raise RuntimeError(f"Migrated schema is missing ORM tables: {sorted(missing)}")
            if "api_idempotency_records" not in tables:
                raise RuntimeError("Idempotency table missing at migration head")
            if "oauth_credentials" not in tables:
                raise RuntimeError("OAuth credential table missing at migration head")
            if "vault_import_sessions" not in tables:
                raise RuntimeError("Vault import session table missing at migration head")
            job_columns = {column["name"] for column in schema.get_columns("ingestion_jobs")}
            if "dedup_key" not in job_columns:
                raise RuntimeError("Ingestion dedup_key missing at migration head")
            if "queued_at_utc" not in job_columns:
                raise RuntimeError("Ingestion queued_at_utc missing at migration head")
            job_indexes = {index["name"] for index in schema.get_indexes("ingestion_jobs")}
            if "ix_ingestion_jobs_user_dedup" not in job_indexes:
                raise RuntimeError("Ingestion dedup index missing at migration head")
            if "ix_ingestion_jobs_user_dispatch" not in job_indexes:
                raise RuntimeError("Ingestion dispatch index missing at migration head")
            transfer_indexes = {index["name"] for index in schema.get_indexes("vault_import_sessions")}
            expected_transfer_indexes = {
                "ix_vault_import_sessions_expires",
                "ix_vault_import_sessions_status",
                "ix_vault_import_sessions_user_created",
                "ix_vault_import_sessions_user_id",
                "ix_vault_import_sessions_user_status",
            }
            missing_transfer_indexes = expected_transfer_indexes - transfer_indexes
            if missing_transfer_indexes:
                raise RuntimeError(f"Vault import indexes missing: {sorted(missing_transfer_indexes)}")
        else:
            if "api_idempotency_records" in tables:
                raise RuntimeError("Idempotency table remained after downgrade")
            if "oauth_credentials" in tables:
                raise RuntimeError("OAuth credential table remained after downgrade")
            job_columns = {column["name"] for column in schema.get_columns("ingestion_jobs")}
            if "dedup_key" in job_columns:
                raise RuntimeError("Ingestion dedup_key remained after downgrade")
            if "queued_at_utc" in job_columns:
                raise RuntimeError("Ingestion queued_at_utc remained after downgrade")
    finally:
        engine.dispose()


def _assert_initial_schema(database_url: str) -> None:
    engine = create_engine(database_url)
    try:
        schema = inspect(engine)
        tables = set(schema.get_table_names())
        later_tables = {
            "api_idempotency_records",
            "app_devices",
            "chat_conversations",
            "chat_messages",
            "document_chunks",
            "document_sources",
            "pending_chat_actions",
            "oauth_credentials",
            "safety_reports",
        }
        unexpected = sorted(tables & later_tables)
        if unexpected:
            raise RuntimeError(f"Revision 0001 leaked later tables: {unexpected}")
        job_columns = {column["name"] for column in schema.get_columns("ingestion_jobs")}
        raw_columns = {column["name"] for column in schema.get_columns("raw_entries")}
        entity_columns = {column["name"] for column in schema.get_columns("entities")}
        if "dedup_key" in job_columns:
            raise RuntimeError("Revision 0001 leaked ingestion dedup_key")
        if "queued_at_utc" in job_columns:
            raise RuntimeError("Revision 0001 leaked ingestion queued_at_utc")
        if {"user_importance", "contextual_salience", "analysis_json"} & raw_columns:
            raise RuntimeError("Revision 0001 leaked later raw-entry columns")
        if {"salience_score", "salience_signals_json"} & entity_columns:
            raise RuntimeError("Revision 0001 leaked later entity salience columns")
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
