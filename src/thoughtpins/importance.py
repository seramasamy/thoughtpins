"""Explicit user importance for journal and source entries.

Importance is a preference signal, not a truth or relevance score. Retrieval
uses it as a bounded prior so exact evidence still wins.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from thoughtpins.db import AuditLog, IngestionJob, RawEntry, User

MIN_IMPORTANCE = 1
MAX_IMPORTANCE = 5
IMPORTANCE_BONUS = {
    1: -0.01,
    2: 0.0,
    3: 0.015,
    4: 0.035,
    5: 0.06,
}


@dataclass(frozen=True)
class ImportanceUpdate:
    target_type: str
    target_id: str
    previous_importance: int | None
    user_importance: int | None
    changed: bool
    entry_id: str | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_user_importance(value: Any) -> int | None:
    """Return a valid nullable 1-5 rating or raise a stable validation error."""
    if value is None or (isinstance(value, str) and value.strip().lower() in {"", "none", "null", "clear"}):
        return None
    if isinstance(value, bool):
        raise ValueError("Importance must be a number from 1 to 5 or null")
    try:
        rating = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Importance must be a number from 1 to 5 or null") from exc
    if rating < MIN_IMPORTANCE or rating > MAX_IMPORTANCE:
        raise ValueError("Importance must be between 1 and 5")
    return rating


def importance_bonus(value: int | None) -> float:
    """Return the deliberately small retrieval contribution for a rating."""
    return IMPORTANCE_BONUS.get(value, 0.0) if value is not None else 0.0


def importance_label(value: int | None) -> str:
    return "Unrated" if value is None else f"{value} of 5"


def set_entry_importance(
    session: Session,
    *,
    user_id: str,
    entry_id: str,
    value: int | None,
    source: str = "user",
    conversation_key: str = "",
) -> ImportanceUpdate | None:
    """Set an owned entry's rating and append a reversible audit event."""
    rating = normalize_user_importance(value)
    entry = (
        session.query(RawEntry)
        .filter(
            RawEntry.id == entry_id,
            RawEntry.user_id == user_id,
        )
        .first()
    )
    if not entry:
        return None

    previous = normalize_user_importance(entry.user_importance)
    changed = previous != rating
    if changed:
        entry.user_importance = rating
        entry.importance_source = (source or "user")[:32]
        entry.importance_updated_at = _utcnow()
        _append_importance_event(
            session,
            user_id=user_id,
            action="entry.importance.updated",
            metadata={
                "entry_id": entry.id,
                "previous_importance": previous,
                "new_importance": rating,
                "source": (source or "user")[:32],
                "conversation_key": conversation_key[:128],
                "undone": False,
            },
        )
        _refresh_derived_salience(session, entry)
    return ImportanceUpdate("entry", entry.id, previous, rating, changed, entry_id=entry.id)


def set_latest_importance(
    session: Session,
    *,
    user_id: str,
    value: int | None,
    conversation_key: str = "",
    source: str = "natural_language",
) -> ImportanceUpdate | None:
    """Rate the latest structured save, falling back to an active ingest job."""
    query = session.query(RawEntry).filter(
        RawEntry.user_id == user_id,
        RawEntry.processed_status != "conversation",
    )
    if conversation_key:
        scoped = (
            query.filter(RawEntry.telegram_chat_id == conversation_key)
            .order_by(RawEntry.created_at_utc.desc(), RawEntry.id.desc())
            .first()
        )
        if scoped:
            return set_entry_importance(
                session,
                user_id=user_id,
                entry_id=scoped.id,
                value=value,
                source=source,
                conversation_key=conversation_key,
            )

    entry = query.order_by(RawEntry.created_at_utc.desc(), RawEntry.id.desc()).first()
    if entry:
        return set_entry_importance(
            session,
            user_id=user_id,
            entry_id=entry.id,
            value=value,
            source=source,
            conversation_key=conversation_key,
        )

    jobs = (
        session.query(IngestionJob)
        .filter(
            IngestionJob.user_id == user_id,
            IngestionJob.status.in_(["pending", "retry", "queued", "running"]),
        )
        .order_by(IngestionJob.created_at_utc.desc())
        .limit(30)
        .all()
    )
    for job in jobs:
        metadata = dict(job.metadata_json or {})
        if conversation_key and metadata.get("conversation_key") not in {None, "", conversation_key}:
            continue
        previous = normalize_user_importance(metadata.get("user_importance"))
        rating = normalize_user_importance(value)
        changed = previous != rating
        if changed:
            metadata["user_importance"] = rating
            metadata["importance_source"] = (source or "natural_language")[:32]
            job.metadata_json = metadata
            _append_importance_event(
                session,
                user_id=user_id,
                action="job.importance.updated",
                metadata={
                    "job_id": job.id,
                    "previous_importance": previous,
                    "new_importance": rating,
                    "source": (source or "natural_language")[:32],
                    "conversation_key": conversation_key[:128],
                    "undone": False,
                },
            )
        return ImportanceUpdate("job", job.id, previous, rating, changed, entry_id=job.entry_id)
    return None


def undo_latest_importance(
    session: Session,
    *,
    user_id: str,
    conversation_key: str = "",
) -> ImportanceUpdate | None:
    """Undo the latest still-active importance change for this user."""
    events = (
        session.query(AuditLog)
        .filter(
            AuditLog.user_id == user_id,
            AuditLog.action.in_(["entry.importance.updated", "job.importance.updated"]),
        )
        .order_by(AuditLog.created_at_utc.desc(), AuditLog.id.desc())
        .limit(100)
        .all()
    )

    for event in events:
        metadata = dict(event.metadata_json or {})
        if metadata.get("undone") is True:
            continue
        event_conversation = str(metadata.get("conversation_key") or "")
        if conversation_key and event_conversation and event_conversation != conversation_key:
            continue
        previous = normalize_user_importance(metadata.get("previous_importance"))
        current = normalize_user_importance(metadata.get("new_importance"))
        entry_id = str(metadata.get("entry_id") or "")
        target_type = "entry"
        target_id = entry_id

        if event.action == "job.importance.updated":
            target_type = "job"
            target_id = str(metadata.get("job_id") or "")
            job = (
                session.query(IngestionJob)
                .filter(
                    IngestionJob.id == target_id,
                    IngestionJob.user_id == user_id,
                )
                .first()
            )
            if not job:
                continue
            if job.entry_id:
                entry_id = job.entry_id
            else:
                job_metadata = dict(job.metadata_json or {})
                job_metadata["user_importance"] = previous
                job_metadata["importance_source"] = "undo"
                job.metadata_json = job_metadata

        if entry_id:
            entry = (
                session.query(RawEntry)
                .filter(
                    RawEntry.id == entry_id,
                    RawEntry.user_id == user_id,
                )
                .first()
            )
            if not entry:
                continue
            entry.user_importance = previous
            entry.importance_source = "undo"
            entry.importance_updated_at = _utcnow()
            _refresh_derived_salience(session, entry)

        metadata["undone"] = True
        metadata["undone_at_utc"] = _utcnow().isoformat()
        event.metadata_json = metadata
        _append_importance_event(
            session,
            user_id=user_id,
            action="entry.importance.undone" if entry_id else "job.importance.undone",
            metadata={
                "entry_id": entry_id or None,
                "job_id": target_id if target_type == "job" else None,
                "restored_importance": previous,
                "reverted_importance": current,
                "conversation_key": conversation_key[:128],
            },
        )
        return ImportanceUpdate(target_type, target_id, current, previous, True, entry_id=entry_id or None)
    return None


def importance_prompts_enabled(session: Session, *, user_id: str) -> bool:
    user = session.query(User).filter(User.id == user_id).first()
    if not user:
        return False
    prefs = dict(user.preferences_json or {})
    app_prefs = dict(prefs.get("app_preferences") or {})
    return app_prefs.get("importance_prompts_enabled") is True


def set_importance_prompts_enabled(session: Session, *, user_id: str, enabled: bool) -> bool:
    user = session.query(User).filter(User.id == user_id).first()
    if not user:
        return False
    prefs = dict(user.preferences_json or {})
    app_prefs = dict(prefs.get("app_preferences") or {})
    app_prefs["importance_prompts_enabled"] = bool(enabled)
    app_prefs["updated_at_utc"] = _utcnow().isoformat()
    prefs["app_preferences"] = app_prefs
    user.preferences_json = prefs
    _append_importance_event(
        session,
        user_id=user_id,
        action="preferences.importance_prompts.updated",
        metadata={"enabled": bool(enabled)},
    )
    return True


def should_prompt_for_importance(text: str, stats: dict[str, Any]) -> bool:
    """Prompt only for substantial captures when the user opted in."""
    if len((text or "").strip()) >= 320:
        return True
    return any(int(stats.get(key, 0) or 0) > 0 for key in ("events", "action_items", "relationships"))


def _append_importance_event(
    session: Session,
    *,
    user_id: str,
    action: str,
    metadata: dict[str, Any],
) -> None:
    session.add(AuditLog(user_id=user_id, action=action, metadata_json=metadata))


def _refresh_derived_salience(session: Session, entry: RawEntry) -> None:
    # Imported lazily to keep the explicit preference API independent from the
    # extraction stack while still keeping derived cards immediately current.
    from thoughtpins.memory.salience_store import refresh_salience_after_importance_change

    refresh_salience_after_importance_change(session, entry)
