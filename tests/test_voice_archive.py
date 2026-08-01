from __future__ import annotations

import base64
import json
import os
import time
from datetime import date

import pytest

from thoughtpins.chat.engine import ChatEngineResult
from thoughtpins.media import MediaExtraction


def _audio_payload(content: bytes = b"compressed-audio-fixture") -> dict[str, str]:
    return {
        "filename": "voice-note.m4a",
        "media_type": "audio/mp4",
        "destination": "journal",
        "content_base64": base64.b64encode(content).decode("ascii"),
    }


def _consent_payload() -> dict[str, bool]:
    return {
        "retain_recordings": True,
        "acknowledge_sensitive_audio": True,
        "acknowledge_personal_use_only": True,
        "acknowledge_deletion_available": True,
    }


def _stub_transcription(monkeypatch, text: str = "I met Maya for coffee today.") -> None:
    from thoughtpins import uploads

    monkeypatch.setattr(
        uploads,
        "transcribe_audio",
        lambda content, suffix: MediaExtraction(
            text=text,
            kind="audio",
            metadata={"processing": "local", "language": "en"},
        ),
    )


def _entry_for_default_user(entry_id: str) -> str:
    from thoughtpins.db import RawEntry, User
    from thoughtpins.store import get_session
    from thoughtpins.utils import hash_text

    session = get_session()
    try:
        user = session.query(User).one()
        transcript = "I met Maya for coffee today."
        session.add(
            RawEntry(
                id=entry_id,
                user_id=user.id,
                local_date=date(2026, 7, 13),
                raw_text=transcript,
                content_hash=hash_text(transcript),
                source="voice_test",
                processed_status="completed",
            )
        )
        session.commit()
        return user.id
    finally:
        session.close()


def test_voice_upload_is_ephemeral_by_default_and_audited(isolated_db, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from thoughtpins import uploads
    from thoughtpins.api import app
    from thoughtpins.config import config
    from thoughtpins.db import AuditLog, VoiceAsset
    from thoughtpins.store import get_session

    monkeypatch.setattr(config, "VOICE_ARCHIVE_PATH", tmp_path / "voice")
    monkeypatch.setattr(type(config), "VOICE_ARCHIVE_PATH", tmp_path / "voice")
    _stub_transcription(monkeypatch)
    monkeypatch.setattr(
        uploads,
        "execute_chat_message",
        lambda *args, **kwargs: ChatEngineResult(
            status="ok", route_type="journal_entry", reply="Saved.", entry_id="ephemeral-entry"
        ),
    )

    response = TestClient(app).post("/v1/uploads", json=_audio_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["media_kind"] == "audio"
    assert body["attachment_saved"] is False
    assert body["attachment_ref"] is None
    assert body["voice_asset_id"] is None
    assert body["metadata"]["voice_archive"]["reason"] == "consent_not_enabled"
    assert not list((tmp_path / "voice").rglob("*"))

    session = get_session()
    try:
        assert session.query(VoiceAsset).count() == 0
        event = session.query(AuditLog).filter(AuditLog.action == "voice.note.processed").one()
        encoded = json.dumps(event.metadata_json)
        assert "I met Maya" not in encoded
        assert event.metadata_json["voice_retained"] is False
    finally:
        session.close()


def test_voice_archive_requires_complete_explicit_consent(isolated_db, monkeypatch):
    from fastapi.testclient import TestClient

    from thoughtpins.api import app
    from thoughtpins.config import config

    client = TestClient(app)
    client.get("/v1/me")
    partial = _consent_payload()
    partial["acknowledge_sensitive_audio"] = False
    rejected = client.post("/v1/voice-archive/consent", json=partial)
    assert rejected.status_code == 400

    monkeypatch.setattr(config, "DATA_ENCRYPTION_KEY", "")
    monkeypatch.setattr(type(config), "DATA_ENCRYPTION_KEY", "")
    unavailable = client.post("/v1/voice-archive/consent", json=_consent_payload())
    assert unavailable.status_code == 503


def test_voice_archive_encrypts_redacts_and_deletes(isolated_db, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from thoughtpins import uploads
    from thoughtpins.api import app
    from thoughtpins.config import config
    from thoughtpins.db import VoiceAsset
    from thoughtpins.store import get_session
    from thoughtpins.voice_archive import decode_voice_payload

    archive_root = tmp_path / "voice"
    monkeypatch.setattr(config, "VOICE_ARCHIVE_PATH", archive_root)
    monkeypatch.setattr(type(config), "VOICE_ARCHIVE_PATH", archive_root)
    _stub_transcription(monkeypatch)
    entry_id = "retained_voice_entry"
    client = TestClient(app)
    client.get("/v1/me")
    user_id = _entry_for_default_user(entry_id)
    monkeypatch.setattr(
        uploads,
        "execute_chat_message",
        lambda *args, **kwargs: ChatEngineResult(
            status="ok", route_type="journal_entry", reply="Saved.", entry_id=entry_id
        ),
    )

    consent = client.post("/v1/voice-archive/consent", json=_consent_payload())
    assert consent.status_code == 200
    assert consent.json()["enabled"] is True

    plaintext = b"recognizable-voice-binary-canary"
    uploaded = client.post("/v1/uploads", json=_audio_payload(plaintext))
    assert uploaded.status_code == 200
    body = uploaded.json()
    assert body["attachment_saved"] is True
    assert body["attachment_ref"] is None
    assert body["voice_asset_id"]

    session = get_session()
    try:
        asset = session.query(VoiceAsset).filter_by(user_id=user_id).one()
        path = (archive_root / asset.storage_ref).resolve()
        encrypted = path.read_bytes()
        assert plaintext not in encrypted
        assert decode_voice_payload(encrypted, user_id=user_id) == plaintext
        assert asset.raw_entry_id == entry_id
        assert asset.transcription_mode == "local"
        assert asset.storage_codec == "fernet+zlib-v1"
        assert asset.content_fingerprint != plaintext.hex()
    finally:
        session.close()

    exported = client.get("/v1/export")
    assert exported.status_code == 200
    encoded_export = json.dumps(exported.json(), sort_keys=True)
    exported_asset = exported.json()["tables"]["voice_assets"][0]
    assert "storage_ref" not in exported_asset
    assert "content_fingerprint" not in exported_asset
    assert "recognizable-voice-binary-canary" not in encoded_export

    disabled = client.delete("/v1/voice-archive/consent")
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    assert disabled.json()["asset_count"] == 1

    wrong = client.request("DELETE", "/v1/voice-archive", json={"confirm": "DELETE"})
    assert wrong.status_code == 400
    deleted = client.request("DELETE", "/v1/voice-archive", json={"confirm": "DELETE VOICE ARCHIVE"})
    assert deleted.status_code == 200
    assert deleted.json()["deleted"]["voice_assets"] == 1
    assert not any(path.is_file() for path in archive_root.rglob("*"))

    session = get_session()
    try:
        assert session.query(VoiceAsset).count() == 0
    finally:
        session.close()


def test_unrecognized_audio_is_never_retained(isolated_db, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from thoughtpins import uploads
    from thoughtpins.api import app
    from thoughtpins.config import config
    from thoughtpins.db import VoiceAsset
    from thoughtpins.store import get_session

    monkeypatch.setattr(config, "VOICE_ARCHIVE_PATH", tmp_path / "voice")
    monkeypatch.setattr(type(config), "VOICE_ARCHIVE_PATH", tmp_path / "voice")
    monkeypatch.setattr(
        uploads,
        "transcribe_audio",
        lambda *args, **kwargs: MediaExtraction(kind="audio", error="no_speech_detected"),
    )
    client = TestClient(app)
    client.get("/v1/me")
    assert client.post("/v1/voice-archive/consent", json=_consent_payload()).status_code == 200
    response = client.post("/v1/uploads", json=_audio_payload())
    assert response.status_code == 200
    assert response.json()["status"] == "needs_text"
    assert response.json()["attachment_saved"] is False
    session = get_session()
    try:
        assert session.query(VoiceAsset).count() == 0
    finally:
        session.close()


def test_voice_deletion_is_tenant_scoped_and_account_delete_removes_files(isolated_db, monkeypatch, tmp_path):
    from thoughtpins.config import config
    from thoughtpins.db import RawEntry, User, VoiceAsset
    from thoughtpins.store import get_session
    from thoughtpins.users import register_user
    from thoughtpins.utils import hash_text
    from thoughtpins.voice_archive import delete_voice_archive, enable_voice_archive, retain_voice_note_if_consented

    archive_root = tmp_path / "voice"
    monkeypatch.setattr(config, "VOICE_ARCHIVE_PATH", archive_root)
    monkeypatch.setattr(type(config), "VOICE_ARCHIVE_PATH", archive_root)
    user_a_id = register_user(email="voice-a@example.com").id
    user_b_id = register_user(email="voice-b@example.com").id
    session = get_session()
    try:
        user_a = session.query(User).filter_by(id=user_a_id).one()
        user_b = session.query(User).filter_by(id=user_b_id).one()
        for user, label in ((user_a, "a"), (user_b, "b")):
            enable_voice_archive(user)
            transcript = f"Voice transcript {label}"
            entry = RawEntry(
                id=f"voice_entry_{label}",
                user_id=user.id,
                local_date=date(2026, 7, 13),
                raw_text=transcript,
                content_hash=hash_text(transcript),
                processed_status="completed",
            )
            session.add(entry)
        session.commit()
        first = retain_voice_note_if_consented(
            session,
            user_id=user_a.id,
            content=b"voice-a",
            filename="a.m4a",
            media_type="audio/mp4",
            raw_entry_id="voice_entry_a",
            transcript="Voice transcript a",
            language="en",
            transcription_mode="local",
        )
        second = retain_voice_note_if_consented(
            session,
            user_id=user_b.id,
            content=b"voice-b",
            filename="b.m4a",
            media_type="audio/mp4",
            raw_entry_id="voice_entry_b",
            transcript="Voice transcript b",
            language="en",
            transcription_mode="local",
        )
        assert first.retained and second.retained
        deleted = delete_voice_archive(session, user_a.id)
        assert deleted["voice_assets"] == 1
        assert session.query(VoiceAsset).filter_by(user_id=user_b.id).count() == 1

        from thoughtpins.data_lifecycle import delete_user_data

        removed = delete_user_data(session, user_b.id)
        assert removed["voice_assets"] == 1
        assert not any(path.is_file() for path in archive_root.rglob("*"))
    finally:
        session.close()


def test_voice_archive_rejects_path_escape(isolated_db, monkeypatch, tmp_path):
    from thoughtpins.config import config
    from thoughtpins.voice_archive import VoiceArchiveError, _resolve_storage_ref

    monkeypatch.setattr(config, "VOICE_ARCHIVE_PATH", tmp_path / "voice")
    monkeypatch.setattr(type(config), "VOICE_ARCHIVE_PATH", tmp_path / "voice")
    with pytest.raises(VoiceArchiveError):
        _resolve_storage_ref("../../outside.voice.enc")


def test_public_build_disables_archive_but_keeps_ephemeral_transcription(isolated_db, monkeypatch):
    from fastapi.testclient import TestClient

    from thoughtpins import uploads
    from thoughtpins.api import app
    from thoughtpins.config import config

    monkeypatch.setattr(config, "VOICE_ARCHIVE_ENABLED", False)
    monkeypatch.setattr(type(config), "VOICE_ARCHIVE_ENABLED", False)
    _stub_transcription(monkeypatch)
    monkeypatch.setattr(
        uploads,
        "execute_chat_message",
        lambda *args, **kwargs: ChatEngineResult(
            status="ok", route_type="journal_entry", reply="Saved.", entry_id="public-voice-entry"
        ),
    )
    client = TestClient(app)
    assert client.get("/v1/client-config").json()["voice_archive_enabled"] is False
    assert client.get("/v1/voice-archive").status_code == 404
    uploaded = client.post("/v1/uploads", json=_audio_payload())
    assert uploaded.status_code == 200
    assert uploaded.json()["metadata"]["voice_archive"]["reason"] == "feature_disabled"


def test_deleting_entry_removes_linked_retained_audio(isolated_db, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from thoughtpins import uploads
    from thoughtpins.api import app
    from thoughtpins.config import config
    from thoughtpins.db import VoiceAsset
    from thoughtpins.store import get_session

    archive_root = tmp_path / "voice"
    monkeypatch.setattr(config, "VOICE_ARCHIVE_PATH", archive_root)
    monkeypatch.setattr(type(config), "VOICE_ARCHIVE_PATH", archive_root)
    _stub_transcription(monkeypatch)
    client = TestClient(app)
    client.get("/v1/me")
    entry_id = "linked_voice_entry"
    _entry_for_default_user(entry_id)
    monkeypatch.setattr(
        uploads,
        "execute_chat_message",
        lambda *args, **kwargs: ChatEngineResult(
            status="ok", route_type="journal_entry", reply="Saved.", entry_id=entry_id
        ),
    )
    assert client.post("/v1/voice-archive/consent", json=_consent_payload()).status_code == 200
    assert client.post("/v1/uploads", json=_audio_payload()).json()["voice_asset_id"]
    assert client.delete(f"/v1/entries/{entry_id}").status_code == 200

    session = get_session()
    try:
        assert session.query(VoiceAsset).count() == 0
        assert not any(path.is_file() for path in archive_root.rglob("*"))
    finally:
        session.close()


def test_voice_fingerprints_are_tenant_scoped(monkeypatch):
    from thoughtpins.config import config
    from thoughtpins.crypto import fingerprint_bytes
    from thoughtpins.voice_archive import _voice_scope

    # Fingerprinting returns None without a master key, so the test has to
    # supply one. It took no fixtures, so on a checkout with no configured key
    # every assertion below was comparing None to None.
    key = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
    monkeypatch.setattr(config, "DATA_ENCRYPTION_KEY", key)
    monkeypatch.setattr(type(config), "DATA_ENCRYPTION_KEY", key)

    content = b"same-recording"
    first = fingerprint_bytes(content, scope=_voice_scope("user-a"))
    second = fingerprint_bytes(content, scope=_voice_scope("user-b"))

    assert first
    assert second
    assert first != second


def test_voice_archive_cleans_old_orphans_and_reports_missing_files(isolated_db, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from thoughtpins.api import app
    from thoughtpins.config import config
    from thoughtpins.db import User, VoiceAsset
    from thoughtpins.store import get_session
    from thoughtpins.voice_archive import (
        ORPHAN_GRACE_SECONDS,
        VOICE_ARCHIVE_CONSENT_VERSION,
        _resolve_storage_ref,
        _storage_ref,
        voice_archive_health,
        voice_archive_status,
    )

    archive_root = tmp_path / "voice"
    monkeypatch.setattr(config, "VOICE_ARCHIVE_PATH", archive_root)
    monkeypatch.setattr(type(config), "VOICE_ARCHIVE_PATH", archive_root)
    TestClient(app).get("/v1/me")

    session = get_session()
    try:
        user = session.query(User).one()
        orphan_ref = _storage_ref(user.id, "orphan")
        orphan_path = _resolve_storage_ref(orphan_ref)
        orphan_path.parent.mkdir(parents=True, exist_ok=True)
        orphan_path.write_bytes(b"untracked-encrypted-fixture")
        old = time.time() - ORPHAN_GRACE_SECONDS - 10
        os.utime(orphan_path, (old, old))

        voice_archive_status(session, user.id)
        assert not orphan_path.exists()

        session.add(
            VoiceAsset(
                id="missing-voice-asset",
                user_id=user.id,
                storage_ref=_storage_ref(user.id, "missing-voice-asset"),
                original_filename="missing.m4a",
                media_type="audio/mp4",
                container="m4a",
                byte_size_original=100,
                byte_size_encrypted=120,
                storage_codec="fernet+zlib-v1",
                content_fingerprint="0" * 64,
                transcript_chars=12,
                transcription_mode="local",
                consent_version=VOICE_ARCHIVE_CONSENT_VERSION,
                retention_purpose="personal_voice_features",
            )
        )
        session.commit()
        health = voice_archive_health(session, user.id)
        assert health["status"] == "error"
        assert health["missing_files"] == 1
        assert "storage_ref" not in health
    finally:
        session.close()
