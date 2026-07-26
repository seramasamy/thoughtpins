"""Frozen schema used only by Alembic revision 0001.

The first migration must not import the evolving ORM metadata wholesale. This
allowlist preserves deterministic rebuilds while retaining SQLAlchemy's column
and foreign-key definitions for the original tables.
"""

from __future__ import annotations

import warnings

from sqlalchemy import Index, MetaData, Table

from thoughtpins.db import Base

INITIAL_COLUMNS: dict[str, tuple[str, ...]] = {
    "users": (
        "id",
        "email",
        "phone",
        "display_name",
        "password_hash",
        "api_key",
        "telegram_chat_id",
        "is_active",
        "is_admin",
        "created_at_utc",
        "last_login_utc",
        "deleted_at_utc",
        "auth_method",
        "two_factor_enabled",
        "two_factor_secret",
        "preferences_json",
    ),
    "auth_sessions": (
        "id",
        "user_id",
        "refresh_token_hash",
        "created_at_utc",
        "expires_at_utc",
        "revoked_at_utc",
        "replaced_by_session_id",
        "user_agent",
        "ip_address",
    ),
    "ingestion_jobs": (
        "id",
        "user_id",
        "status",
        "source",
        "raw_text",
        "entry_id",
        "error",
        "created_at_utc",
        "started_at_utc",
        "finished_at_utc",
        "metadata_json",
    ),
    "audit_logs": ("id", "user_id", "action", "created_at_utc", "metadata_json"),
    "raw_entries": (
        "id",
        "user_id",
        "created_at_utc",
        "local_date",
        "local_time",
        "source",
        "telegram_message_id",
        "telegram_chat_id",
        "author_user_id",
        "raw_text",
        "content_hash",
        "is_private",
        "sensitivity",
        "processed_status",
        "processing_error",
    ),
    "entities": (
        "id",
        "user_id",
        "type",
        "canonical_name",
        "aliases_json",
        "created_at_utc",
        "updated_at_utc",
        "sensitivity",
        "confidence",
        "notes",
        "attributes_json",
    ),
    "entity_mentions": (
        "id",
        "user_id",
        "raw_entry_id",
        "entity_id",
        "surface_text",
        "mention_context",
        "confidence",
    ),
    "memories": (
        "id",
        "user_id",
        "raw_entry_id",
        "memory_type",
        "subject_entity_id",
        "object_entity_id",
        "predicate",
        "text",
        "structured_json",
        "occurred_at_start",
        "occurred_at_end",
        "local_date",
        "sensitivity",
        "confidence",
        "source_provenance",
        "valid_from",
        "valid_to",
        "supersedes_memory_id",
        "created_at_utc",
    ),
    "relationships": (
        "id",
        "user_id",
        "source_entity_id",
        "target_entity_id",
        "relation_type",
        "raw_entry_id",
        "memory_id",
        "weight",
        "confidence",
        "sensitivity",
        "first_seen_at",
        "last_seen_at",
        "evidence_count",
        "notes",
    ),
    "events": (
        "id",
        "user_id",
        "name",
        "event_type",
        "start_at",
        "end_at",
        "local_date",
        "place_entity_id",
        "summary",
        "sensitivity",
        "source_raw_entry_id",
    ),
    "event_participants": ("id", "user_id", "event_id", "entity_id", "role"),
    "action_items": (
        "id",
        "user_id",
        "raw_entry_id",
        "description",
        "due_at",
        "owner_entity_id",
        "status",
        "sensitivity",
    ),
    "expenses": (
        "id",
        "user_id",
        "raw_entry_id",
        "amount",
        "currency",
        "merchant_or_place_entity_id",
        "reason",
        "category",
        "confidence",
    ),
    "reports": (
        "id",
        "user_id",
        "created_at_utc",
        "query",
        "report_type",
        "output_markdown_path",
        "output_pdf_path",
        "output_html_path",
        "source_memory_ids_json",
        "source_raw_entry_ids_json",
    ),
}


def build_initial_metadata() -> MetaData:
    metadata = MetaData()
    for table_name, column_names in INITIAL_COLUMNS.items():
        source = Base.metadata.tables[table_name]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=DeprecationWarning)
            columns = [source.c[name]._copy() for name in column_names]
        target = Table(table_name, metadata, *columns)
        existing_indexes = {index.name for index in target.indexes}
        for source_index in source.indexes:
            names = [getattr(expression, "name", None) for expression in source_index.expressions]
            if not source_index.name or source_index.name in existing_indexes or not all(names):
                continue
            if not set(names).issubset(column_names):
                continue
            Index(source_index.name, *(target.c[name] for name in names), unique=source_index.unique)
    return metadata
