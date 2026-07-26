"""User data export and deletion helpers."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from thoughtpins.crypto import maybe_decrypt_text
from thoughtpins.db import (
    ActionItem,
    ApiIdempotencyRecord,
    AppDevice,
    AuditLog,
    AuthSession,
    ChatConversation,
    ChatMessage,
    DocumentChunk,
    DocumentSource,
    Entity,
    EntityMention,
    Event,
    EventParticipant,
    Expense,
    IngestionJob,
    Memory,
    OAuthCredential,
    PendingChatAction,
    RawEntry,
    Relationship,
    Report,
    SafetyReport,
    User,
    VoiceAsset,
)
from thoughtpins.source_policy import SourceExportPolicy, export_policy_for_source

INTERNAL_EXPORT_KEYS = {
    "api_key",
    "password_hash",
    "refresh_token_hash",
    "token_hash",
    "push_token_hash",
    "push_token_encrypted",
    "two_factor_secret",
    "content_hash",
    "content_fingerprint",
    "oauth_profiles",
    "storage_ref",
}


class DataDeletionUnavailable(RuntimeError):
    """Raised when a required external cleanup cannot complete safely."""


EXPORT_MODELS = [
    RawEntry,
    Entity,
    EntityMention,
    Memory,
    Relationship,
    Event,
    EventParticipant,
    ActionItem,
    Expense,
    DocumentSource,
    DocumentChunk,
    ChatConversation,
    ChatMessage,
    PendingChatAction,
    Report,
    SafetyReport,
    IngestionJob,
    AppDevice,
    AuditLog,
    VoiceAsset,
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _row_to_dict(row) -> dict[str, Any]:
    payload = {column.name: _jsonable(getattr(row, column.name)) for column in row.__table__.columns}
    if "raw_text" in payload and isinstance(payload["raw_text"], str):
        payload["raw_text"] = maybe_decrypt_text(payload["raw_text"])
    sanitized = _sanitize_export_value(payload)
    return sanitized if isinstance(sanitized, dict) else {}


def _sanitize_export_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize_export_value(item)
            for key, item in value.items()
            if not _is_internal_export_key(str(key))
        }
    if isinstance(value, list):
        return [_sanitize_export_value(item) for item in value]
    return value


def _is_internal_export_key(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized in INTERNAL_EXPORT_KEYS or normalized.endswith("_hash") or normalized.endswith("_encrypted")


def export_user_data(session: Session, user_id: str) -> dict[str, Any]:
    user = session.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("User not found")

    payload: dict[str, Any] = {
        "exported_at_utc": _utcnow().isoformat(),
        "user": _row_to_dict(user),
        "tables": {},
    }
    payload["user"].pop("password_hash", None)
    payload["user"].pop("api_key", None)

    documents = session.query(DocumentSource).filter(DocumentSource.user_id == user_id).all()
    documents_by_id = {document.id: document for document in documents}
    documents_by_entry_id = {document.raw_entry_id: document for document in documents}
    source_policies = {document.id: export_policy_for_source(document) for document in documents}
    excluded_source_ids = sorted(
        document_id for document_id, policy in source_policies.items() if not policy.include_source_text
    )
    payload["source_export_policy"] = {
        "third_party_source_text": "excluded",
        "excluded_source_count": len(excluded_source_ids),
        "included_source_count": len(source_policies) - len(excluded_source_ids),
        "portable_content": "source metadata, provenance, reusable-rights text, and user memory",
    }

    for model in EXPORT_MODELS:
        rows = session.query(model).filter(model.user_id == user_id).all()
        exported_rows: list[dict[str, Any]] = []
        for row in rows:
            if isinstance(row, DocumentChunk):
                policy = source_policies.get(row.document_id)
                if policy is not None and not policy.include_source_chunks:
                    continue
            if isinstance(row, Memory):
                document_id = _document_id_from_provenance(row.source_provenance)
                policy = source_policies.get(document_id or "")
                if policy is not None and row.memory_type == "source_excerpt" and not policy.include_source_chunks:
                    continue

            exported = _row_to_dict(row)
            if isinstance(row, DocumentSource):
                exported = _portable_document_row(exported, source_policies[row.id])
            elif isinstance(row, RawEntry):
                document = documents_by_entry_id.get(row.id)
                if document is not None and not source_policies[document.id].include_source_text:
                    exported["raw_text"] = _portable_source_reference(document)
            elif isinstance(row, Memory):
                document_id = _document_id_from_provenance(row.source_provenance)
                document = documents_by_id.get(document_id or "")
                policy = source_policies.get(document_id or "")
                if document is not None and policy is not None and not policy.include_extractive_summary:
                    if row.memory_type == "source_summary":
                        exported["text"] = _portable_source_reference(document)
            exported_rows.append(exported)
        payload["tables"][model.__tablename__] = exported_rows

    return payload


def _portable_document_row(payload: dict[str, Any], policy: SourceExportPolicy) -> dict[str, Any]:
    payload["source_text_included"] = policy.include_source_text
    payload["source_text_policy"] = policy.reason
    if policy.include_source_text:
        return payload
    payload.pop("raw_text", None)
    payload.pop("summary", None)
    metadata = payload.get("metadata_json")
    if isinstance(metadata, dict):
        payload["metadata_json"] = {
            key: value
            for key, value in metadata.items()
            if key not in {"user_note", "raw_text", "content", "html", "markdown"}
        }
    return payload


def _portable_source_reference(document: DocumentSource) -> str:
    parts = [f"Saved source: {document.title}"]
    if document.source_domain:
        parts.append(f"Publisher: {document.source_domain}")
    if document.source_url or document.original_url:
        parts.append(f"URL: {document.source_url or document.original_url}")
    parts.append("Third-party source text is intentionally excluded from portable exports.")
    return "\n".join(parts)


def _document_id_from_provenance(value: str | None) -> str | None:
    prefix = "document:"
    return value[len(prefix) :] if value and value.startswith(prefix) else None


def delete_user_data(session: Session, user_id: str) -> dict[str, int]:
    """Delete all user-owned data and deactivate the user account."""
    from thoughtpins.voice_archive import delete_voice_archive

    # Serialize deletion against ingestion/chat writes. PostgreSQL writers use
    # a shared lock on this row and recheck active state before their final
    # commit; deletion owns the exclusive lock through every cleanup stage.
    with session.no_autoflush:
        user = session.query(User).filter(User.id == user_id).with_for_update().first()
    memory_ids = [row[0] for row in session.query(Memory.id).filter(Memory.user_id == user_id).all()]
    if memory_ids:
        try:
            from thoughtpins.memory.vector_store import get_vector_store

            get_vector_store().delete(memory_ids)
        except Exception as exc:
            session.rollback()
            raise DataDeletionUnavailable(
                "Derived memory cleanup is temporarily unavailable; the account was not deleted."
            ) from exc

    deleted: dict[str, int] = delete_voice_archive(session, user_id, commit=False)

    ordered_models = [
        ApiIdempotencyRecord,
        EventParticipant,
        EntityMention,
        ActionItem,
        Expense,
        Relationship,
        Memory,
        DocumentChunk,
        ChatMessage,
        PendingChatAction,
        ChatConversation,
        DocumentSource,
        Event,
        Report,
        SafetyReport,
        IngestionJob,
        AppDevice,
        OAuthCredential,
        AuthSession,
        RawEntry,
        Entity,
        AuditLog,
    ]

    for model in ordered_models:
        count = session.query(model).filter(model.user_id == user_id).delete(synchronize_session=False)
        deleted[model.__tablename__] = count

    if user:
        user.is_active = False
        user.deleted_at_utc = _utcnow()
        user.api_key = f"deleted_{user.id}"
        user.password_hash = None
        user.telegram_chat_id = None
        user.email = None
        user.phone = None
        user.display_name = "Deleted User"
        deleted["users"] = 1
    else:
        deleted["users"] = 0

    session.commit()
    return deleted
