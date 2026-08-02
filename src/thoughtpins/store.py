"""SQLAlchemy database setup and session management."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from thoughtpins.config import config
from thoughtpins.tenancy import get_current_tenant_id

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        db_url = config.database_url_sync()
        engine_kwargs: dict[str, Any] = {
            "echo": False,
            "future": True,
            "pool_pre_ping": True,
        }

        if db_url.startswith("sqlite:///"):
            db_path = config.database_path()
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            engine_kwargs["connect_args"] = {"check_same_thread": False}
        else:
            engine_kwargs["pool_size"] = config.DB_POOL_SIZE
            engine_kwargs["max_overflow"] = config.DB_MAX_OVERFLOW
            engine_kwargs["pool_recycle"] = config.DB_POOL_RECYCLE_SECONDS

        _engine = create_engine(db_url, **engine_kwargs)

        if _engine.dialect.name == "sqlite":

            @event.listens_for(_engine, "connect")
            def _set_sqlite_pragma(dbapi_connection, _connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

    return _engine


def get_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        engine = get_engine()
        _SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return _SessionLocal()


@event.listens_for(Session, "after_begin")
def _set_postgres_tenant_context(_session: Session, _transaction, connection) -> None:
    """Set the PostgreSQL RLS tenant variable for sessions inside a tenant context."""
    if connection.dialect.name != "postgresql":
        return
    tenant_id = get_current_tenant_id()
    if tenant_id:
        connection.execute(
            text("SELECT set_config('app.current_user_id', :tenant_id, true)"),
            {"tenant_id": tenant_id},
        )


def init_db() -> None:
    problems = config.validate_startup()
    if problems:
        raise RuntimeError("Invalid startup configuration: " + "; ".join(problems))

    from thoughtpins.db import Base

    engine = get_engine()
    if config.AUTO_CREATE_TABLES:
        Base.metadata.create_all(bind=engine)
        _ensure_columns(engine)


def _ensure_columns(engine: Engine) -> None:
    """Add missing SQLite columns for local-dev databases.

    Production databases should use Alembic migrations; this only preserves
    existing local SQLite data while the model evolves.
    """
    if engine.dialect.name != "sqlite":
        return

    desired_columns = {
        "users": {
            "password_hash": "VARCHAR(255)",
            "deleted_at_utc": "DATETIME",
        },
        "raw_entries": {
            "user_id": "VARCHAR(32) REFERENCES users(id)",
            "analysis_json": "JSON",
            "contextual_salience": "FLOAT",
            "salience_uncertainty": "FLOAT",
            "salience_model_version": "VARCHAR(32)",
            "salience_updated_at": "DATETIME",
        },
        "ingestion_jobs": {
            "queued_at_utc": "DATETIME",
        },
        "entities": {
            "user_id": "VARCHAR(32) REFERENCES users(id)",
            "salience_score": "FLOAT",
            "salience_uncertainty": "FLOAT",
            "salience_signals_json": "JSON",
            "salience_model_version": "VARCHAR(32)",
            "salience_updated_at": "DATETIME",
        },
        "entity_mentions": {
            "user_id": "VARCHAR(32) REFERENCES users(id)",
        },
        "memories": {
            "user_id": "VARCHAR(32) REFERENCES users(id)",
        },
        "relationships": {
            "user_id": "VARCHAR(32) REFERENCES users(id)",
        },
        "events": {
            "user_id": "VARCHAR(32) REFERENCES users(id)",
        },
        "event_participants": {
            "user_id": "VARCHAR(32) REFERENCES users(id)",
        },
        "action_items": {
            "user_id": "VARCHAR(32) REFERENCES users(id)",
        },
        "expenses": {
            "user_id": "VARCHAR(32) REFERENCES users(id)",
        },
        "reports": {
            "user_id": "VARCHAR(32) REFERENCES users(id)",
        },
        "document_sources": {
            "original_url": "TEXT",
            "source_domain": "VARCHAR(255)",
            "access_method": "VARCHAR(32)",
            "rights_basis": "VARCHAR(32)",
            "fetch_status": "VARCHAR(32)",
            "paywall_detected": "BOOLEAN DEFAULT 0",
            "retrieval_quality_score": "FLOAT",
            "published_at": "DATETIME",
        },
        "document_chunks": {
            "token_count": "INTEGER",
            "embedding_id": "VARCHAR(128)",
            "section_heading": "VARCHAR(255)",
        },
    }

    with engine.begin() as conn:
        for table_name, columns in desired_columns.items():
            table_exists = conn.exec_driver_sql(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
                (table_name,),
            ).fetchone()
            if not table_exists:
                continue

            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()}
            for column_name, column_sql in columns.items():
                if column_name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")


@contextmanager
def tenant_session(user_id: str) -> Iterator[Session]:
    """A session whose transaction really is scoped to this tenant.

    The tenant variable is applied by an ``after_begin`` hook, which fires once
    when a transaction opens. Nesting ``tenant_context`` inside a request that
    already has an open transaction therefore changes the context variable but
    never reaches PostgreSQL, so the queries keep running as the original user
    and quietly return that user's rows instead of the requested tenant's.

    Opening a fresh session inside the context makes the hook fire with the
    tenant that was asked for. Operator-facing code that walks tenants has to
    use this; on SQLite there is no row-level security and it behaves the same.
    """
    from thoughtpins.tenancy import tenant_context

    with tenant_context(user_id):
        session = get_session()
        try:
            yield session
        finally:
            session.close()
