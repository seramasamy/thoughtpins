"""User data export and deletion helpers."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
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
    InviteRequest,
    LlmUsageEvent,
    Memory,
    OAuthCredential,
    PendingChatAction,
    RawEntry,
    Relationship,
    Report,
    SafetyReport,
    User,
    VaultImportSession,
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
# telegram_chat_id is deliberately NOT in this set: it identifies the user's
# own Telegram account, which is their data to take with them, the same way
# their email address is exported.


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


def _purge_user_files(session: Session, user_id: str, user: User | None) -> None:
    """Remove this account's content from stores no row cascade reaches.

    Runs while the user row still holds its identifiers: the conversation
    cache is keyed by telegram_chat_id and magic-link tokens by email, so both
    must be resolved before the tombstone nulls them.
    """
    import shutil

    from thoughtpins.config import config

    # Generated report files. The rows record where they were written.
    for report in session.query(Report).filter(Report.user_id == user_id).all():
        for path_text in (report.output_markdown_path, report.output_pdf_path, report.output_html_path):
            if path_text:
                Path(path_text).unlink(missing_ok=True)
    # Reports are also written under a per-user directory (api_routes/exports
    # and the Telegram bot), which the rows do not always record.
    shutil.rmtree(config.reports_path() / user_id, ignore_errors=True)

    # The vault projection, its export zip, and graph visual exports.
    from thoughtpins.vault.export_support import clean_generated_vault

    vault_root = config.vault_path()
    user_vault = vault_root / user_id
    if user_vault.exists():
        clean_generated_vault(user_vault, vault_root, user_id)
    (vault_root / f"{user_id}.zip").unlink(missing_ok=True)
    shutil.rmtree(vault_root / "_system" / "graph_exports" / user_id, ignore_errors=True)

    # Staged vault-import archives. The expiry sweep only serves active
    # accounts, so without this a deleted account's uploaded zip stayed
    # forever.
    from thoughtpins.vault.transfers import _remove_archive

    for transfer in session.query(VaultImportSession).filter(VaultImportSession.user_id == user_id).all():
        if transfer.storage_key:
            try:
                _remove_archive(transfer.storage_key)
            except RuntimeError:
                # A malformed storage key names no reachable file; it must not
                # block the deletion of everything else.
                pass

    # Telegram conversation cache, keyed by chat id.
    if user is not None and user.telegram_chat_id:
        from thoughtpins.chat.conversation_state import forget_conversation

        forget_conversation(str(user.telegram_chat_id))

    # Magic-link tokens are deliberately keyed by email, so the user_id purge
    # cannot see them; they would otherwise retain the address as PII until
    # their expiry sweep.
    if user is not None and user.email:
        from thoughtpins.db_platform import MagicLinkToken

        session.query(MagicLinkToken).filter(MagicLinkToken.email == user.email).delete(synchronize_session=False)


def delete_user_data(session: Session, user_id: str) -> dict[str, int]:
    """Delete all user-owned data and deactivate the user account.

    Backups are the one deliberate exception: the daily archive rotation keeps
    up to 14 zips, so deleted content ages out of backups within 14 days
    rather than immediately.
    """
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

    # An auxiliary graph backend can hold episodes that the relational cascades
    # below will never reach, because ingestion writes to it directly. Refuse the
    # deletion rather than report one that did not happen. internal_sql confirms
    # immediately: its rows are deleted by the cascades in this function.
    try:
        from thoughtpins.memory.graph_backend import get_graph_backend

        graph_deleted = get_graph_backend(session).delete_user(user_id)
    except Exception as exc:
        session.rollback()
        raise DataDeletionUnavailable(
            "Graph memory cleanup is temporarily unavailable; the account was not deleted."
        ) from exc
    if not graph_deleted:
        session.rollback()
        raise DataDeletionUnavailable(
            "The configured graph backend cannot confirm removal of this account's episodes; "
            "the account was not deleted."
        )

    deleted: dict[str, int] = delete_voice_archive(session, user_id, commit=False)

    # Content this account left on the FILESYSTEM, which no row cascade can
    # reach. Each of these survived a real deletion until it was looked for:
    # generated report files, the vault projection and its export zip, graph
    # visual exports, staged vault-import archives, and (for Telegram-linked
    # accounts) the on-disk conversation cache. Best effort by design — a
    # missing file is already the desired state — but attempted before the
    # rows go, because the rows are where the paths are recorded.
    _purge_user_files(session, user_id, user)

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
        LlmUsageEvent,
        InviteRequest,
        VaultImportSession,
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
        # The row itself stays as a tombstone so the id cannot be reused and a
        # deletion can be proven to have happened. Everything on it that came
        # from the person goes.
        #
        # preferences_json was the one thing that did not, and it survived a
        # real deletion in testing: it still held the AI-disclosure acceptance,
        # the response-style choice and the private-memory setting. None of
        # that is journal content, but the privacy policy says the account's
        # data is deleted, and "except your settings" is not what it says.
        user.preferences_json = None
        deleted["users"] = 1
    else:
        deleted["users"] = 0

    session.commit()
    return deleted
