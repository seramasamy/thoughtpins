"""Consent, encrypted retention, and deletion for personal voice recordings."""

from __future__ import annotations

import hashlib
import os
import time
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from thoughtpins.config import config
from thoughtpins.crypto import (
    decrypt_bytes_scoped,
    encrypt_bytes_scoped,
    encryption_available,
    fingerprint_bytes,
)
from thoughtpins.db import User, VoiceAsset
from thoughtpins.vault.markdown import safe_filename

VOICE_ARCHIVE_CONSENT_VERSION = "2026-07-13"
VOICE_ARCHIVE_PREFERENCE_KEY = "voice_archive"
VOICE_ARCHIVE_DELETE_CONFIRMATION = "DELETE VOICE ARCHIVE"
VOICE_STORAGE_CODEC = "fernet+zlib-v1"
VOICE_PAYLOAD_PREFIX = b"tp:voice:v1:zlib:"
ORPHAN_GRACE_SECONDS = 60 * 60


class VoiceArchiveError(RuntimeError):
    """Raised when an archive operation cannot honor its privacy contract."""


@dataclass(frozen=True)
class VoiceRetentionOutcome:
    retained: bool
    reason: str
    asset_id: str | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def voice_archive_preference(user: User) -> dict[str, object]:
    stored = dict(user.preferences_json or {})
    value = stored.get(VOICE_ARCHIVE_PREFERENCE_KEY)
    return dict(value) if isinstance(value, dict) else {}


def voice_archive_enabled(user: User) -> bool:
    preference = voice_archive_preference(user)
    return bool(
        config.VOICE_ARCHIVE_ENABLED
        and preference.get("enabled") is True
        and preference.get("consent_version") == VOICE_ARCHIVE_CONSENT_VERSION
    )


def enable_voice_archive(user: User) -> None:
    if not config.VOICE_ARCHIVE_ENABLED:
        raise VoiceArchiveError("Personal voice archive is unavailable in this deployment")
    if not encryption_available():
        raise VoiceArchiveError("Voice archive encryption is unavailable")
    now = _utcnow().isoformat()
    preferences = dict(user.preferences_json or {})
    preferences[VOICE_ARCHIVE_PREFERENCE_KEY] = {
        "enabled": True,
        "consent_version": VOICE_ARCHIVE_CONSENT_VERSION,
        "consented_at_utc": now,
        "disabled_at_utc": None,
        "purpose": "personal_voice_features",
        "affirmations": ["sensitive_audio", "personal_use_only", "deletion_available"],
    }
    user.preferences_json = preferences


def disable_voice_archive(user: User) -> None:
    preferences = dict(user.preferences_json or {})
    current = voice_archive_preference(user)
    current.update({"enabled": False, "disabled_at_utc": _utcnow().isoformat()})
    preferences[VOICE_ARCHIVE_PREFERENCE_KEY] = current
    user.preferences_json = preferences


def voice_archive_status(session: Session, user_id: str) -> dict[str, object]:
    user = session.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("User not found")
    _cleanup_orphaned_files(session, user_id)
    rows = session.query(VoiceAsset).filter(VoiceAsset.user_id == user_id).all()
    preference = voice_archive_preference(user)
    return {
        "enabled": voice_archive_enabled(user),
        "consent_version": preference.get("consent_version"),
        "current_consent_version": VOICE_ARCHIVE_CONSENT_VERSION,
        "consented_at_utc": preference.get("consented_at_utc"),
        "asset_count": len(rows),
        "original_bytes": sum(int(row.byte_size_original or 0) for row in rows),
        "stored_bytes": sum(int(row.byte_size_encrypted or 0) for row in rows),
        "default_processing": "ephemeral",
        "retention_purpose": "personal_voice_features",
        "derived_voice_data_created": any(row.derived_data_status != "not_created" for row in rows),
    }


def voice_archive_health(session: Session, user_id: str) -> dict[str, object]:
    """Return content-free health metadata for the authenticated tenant."""

    if not config.VOICE_ARCHIVE_ENABLED:
        return {"status": "disabled"}
    rows = session.query(VoiceAsset).filter(VoiceAsset.user_id == user_id).all()
    missing = 0
    invalid = 0
    for row in rows:
        try:
            if not _resolve_storage_ref(row.storage_ref).is_file():
                missing += 1
        except VoiceArchiveError:
            invalid += 1
    return {
        "status": "ok" if missing == 0 and invalid == 0 and encryption_available() else "error",
        "encryption_configured": encryption_available(),
        "asset_count": len(rows),
        "missing_files": missing,
        "invalid_references": invalid,
    }


def retain_voice_note_if_consented(
    session: Session,
    *,
    user_id: str,
    content: bytes,
    filename: str,
    media_type: str,
    raw_entry_id: str | None,
    transcript: str,
    language: str | None,
    transcription_mode: str,
) -> VoiceRetentionOutcome:
    """Retain recognizable speech only when current explicit consent is active."""

    if not config.VOICE_ARCHIVE_ENABLED:
        return VoiceRetentionOutcome(False, "feature_disabled")
    if not transcript.strip():
        return VoiceRetentionOutcome(False, "no_speech_detected")
    user = session.query(User).filter(User.id == user_id).first()
    if not user:
        return VoiceRetentionOutcome(False, "user_not_found")
    if not voice_archive_enabled(user):
        return VoiceRetentionOutcome(False, "consent_not_enabled")
    if not encryption_available():
        return VoiceRetentionOutcome(False, "encryption_unavailable")

    encrypted = encode_voice_payload(content, user_id=user_id)
    fingerprint = fingerprint_bytes(content, scope=_voice_scope(user_id))
    if encrypted is None or fingerprint is None:
        return VoiceRetentionOutcome(False, "encryption_unavailable")

    asset_id = uuid4().hex[:16]
    storage_ref = _storage_ref(user_id, asset_id)
    path = _resolve_storage_ref(storage_ref)
    _atomic_write(path, encrypted)
    asset = VoiceAsset(
        id=asset_id,
        user_id=user_id,
        raw_entry_id=raw_entry_id,
        storage_ref=storage_ref,
        original_filename=safe_filename(Path(filename).name, fallback="voice-note", max_length=255),
        media_type=(media_type or None),
        container=Path(filename).suffix.lower().lstrip(".")[:24] or None,
        byte_size_original=len(content),
        byte_size_encrypted=len(encrypted),
        storage_codec=VOICE_STORAGE_CODEC,
        content_fingerprint=fingerprint,
        transcript_chars=len(transcript.strip()),
        transcription_language=(language or None),
        transcription_mode="external" if transcription_mode == "external" else "local",
        consent_version=VOICE_ARCHIVE_CONSENT_VERSION,
        retention_purpose="personal_voice_features",
        derived_data_status="not_created",
    )
    session.add(asset)
    try:
        session.commit()
    except Exception:
        session.rollback()
        path.unlink(missing_ok=True)
        raise
    return VoiceRetentionOutcome(True, "retained", asset_id=asset.id)


def encode_voice_payload(content: bytes, *, user_id: str) -> bytes | None:
    """Compress and encrypt audio in a versioned, tenant-scoped envelope."""

    compressed = zlib.compress(content, level=9)
    return encrypt_bytes_scoped(VOICE_PAYLOAD_PREFIX + compressed, scope=_voice_scope(user_id))


def decode_voice_payload(content: bytes, *, user_id: str) -> bytes | None:
    """Decode retained audio for a future account-scoped feature or integrity test."""

    plaintext = decrypt_bytes_scoped(content, scope=_voice_scope(user_id))
    if plaintext is None or not plaintext.startswith(VOICE_PAYLOAD_PREFIX):
        return None
    try:
        return zlib.decompress(plaintext[len(VOICE_PAYLOAD_PREFIX) :])
    except zlib.error:
        return None


def delete_voice_assets_for_entry(session: Session, *, user_id: str, raw_entry_id: str) -> dict[str, int]:
    """Delete retained audio linked to one entry inside the caller's transaction."""

    rows = (
        session.query(VoiceAsset).filter(VoiceAsset.user_id == user_id, VoiceAsset.raw_entry_id == raw_entry_id).all()
    )
    deleted = _delete_voice_rows(session, rows, commit=False)
    if rows:
        session.flush()
    return deleted


def delete_voice_archive(session: Session, user_id: str, *, commit: bool = True) -> dict[str, int]:
    """Permanently delete retained audio and any future derived voice assets."""

    rows = session.query(VoiceAsset).filter(VoiceAsset.user_id == user_id).all()
    deleted = _delete_voice_rows(session, rows, commit=commit)
    if rows and not commit:
        session.flush()
    _remove_empty_user_directory(user_id)
    return deleted


def _delete_voice_rows(session: Session, rows: list[VoiceAsset], *, commit: bool) -> dict[str, int]:
    deleted_original_bytes = 0
    deleted_stored_bytes = 0
    for row in rows:
        path = _resolve_storage_ref(row.storage_ref)
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise VoiceArchiveError("A retained voice file could not be deleted") from exc
        deleted_original_bytes += int(row.byte_size_original or 0)
        deleted_stored_bytes += int(row.byte_size_encrypted or 0)
        session.delete(row)
    if commit:
        session.commit()
    return {
        "voice_assets": len(rows),
        "original_bytes": deleted_original_bytes,
        "stored_bytes": deleted_stored_bytes,
    }


def _cleanup_orphaned_files(session: Session, user_id: str) -> None:
    """Remove only old, untracked files from the authenticated user's directory."""

    directory = _resolve_storage_ref(_storage_ref(user_id, "placeholder")).parent
    if not directory.is_dir():
        return
    tracked = {
        Path(value).name
        for (value,) in session.query(VoiceAsset.storage_ref).filter(VoiceAsset.user_id == user_id).all()
    }
    cutoff = time.time() - ORPHAN_GRACE_SECONDS
    try:
        candidates = tuple(directory.iterdir())
    except OSError:
        return
    for candidate in candidates:
        try:
            if not candidate.is_file() or candidate.stat().st_mtime >= cutoff:
                continue
            is_orphan = candidate.name.endswith(".voice.enc") and candidate.name not in tracked
            is_stale_temp = candidate.name.startswith(".") and candidate.name.endswith(".tmp")
            if is_orphan or is_stale_temp:
                candidate.unlink(missing_ok=True)
        except OSError:
            # Cleanup is opportunistic. A concurrent delete or locked file must not
            # make the user's archive status endpoint unavailable.
            continue


def _voice_scope(user_id: str) -> str:
    return f"voice-archive:{user_id}"


def _storage_ref(user_id: str, asset_id: str) -> str:
    owner_segment = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:32]
    return f"{owner_segment}/{asset_id}.voice.enc"


def _resolve_storage_ref(storage_ref: str) -> Path:
    root = config.voice_archive_path().resolve()
    path = (root / storage_ref).resolve()
    if path == root or root not in path.parents:
        raise VoiceArchiveError("Voice archive reference escaped its storage root")
    return path


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    finally:
        temporary.unlink(missing_ok=True)


def _remove_empty_user_directory(user_id: str) -> None:
    candidate = _resolve_storage_ref(_storage_ref(user_id, "placeholder")).parent
    try:
        candidate.rmdir()
    except OSError:
        pass
