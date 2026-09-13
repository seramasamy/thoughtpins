from __future__ import annotations

import base64
import secrets

import pytest
from fastapi.testclient import TestClient


def test_originals_never_collide_and_exports_stay_scoped(isolated_db, tmp_path, monkeypatch):
    from thoughtpins.config import config
    from thoughtpins.data_lifecycle import delete_user_data
    from thoughtpins.db import StoredAttachment
    from thoughtpins.media.attachments import export_attachments, save_media_attachment
    from thoughtpins.store import get_session
    from thoughtpins.users import register_user

    monkeypatch.setattr(config, "vault_path", lambda: tmp_path)
    with get_session() as session:
        a = register_user(email="a@example.invalid", session=session, bypass_system_lock=True).id
        b = register_user(email="b@example.invalid", session=session, bypass_system_lock=True).id
        session.commit()
    first = save_media_attachment(b"first original", user_id=a, category="image", filename="photo.png")
    second = save_media_attachment(b"second original", user_id=b, category="image", filename="photo.png")
    third = save_media_attachment(b"third original", user_id=a, category="image", filename="photo.png")
    assert len({first, second, third}) == 3
    exported = tmp_path / "export"
    assert export_attachments(a, exported) == 2
    assert {p.read_bytes() for p in exported.iterdir()} == {b"first original", b"third original"}
    with get_session() as session:
        delete_user_data(session, a)
        assert session.query(StoredAttachment).filter(StoredAttachment.user_id == a).count() == 0
        assert session.query(StoredAttachment).filter(StoredAttachment.user_id == b).count() == 1


def test_attachment_storage_requires_owner_and_rejects_symlinks(tmp_path, monkeypatch):
    from thoughtpins.config import config
    from thoughtpins.media.attachments import attachment_directory, purge_attachments, save_media_attachment
    from thoughtpins.tenancy import tenant_context

    monkeypatch.setattr(config, "vault_path", lambda: tmp_path / "vault")
    with tenant_context(None), pytest.raises(ValueError, match="tenant"):
        save_media_attachment(b"fixture", category="image")
    target = attachment_directory("a")
    target.parent.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    target.symlink_to(outside, target_is_directory=True)
    with pytest.raises(RuntimeError, match="Unsafe"):
        purge_attachments("a")
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("content", [b"An invented original about a violet compass.", bytes(range(32)) * 10])
def test_account_delete_removes_original_even_when_extraction_fails(isolated_db, tmp_path, monkeypatch, content):
    from thoughtpins import library
    from thoughtpins.api import app
    from thoughtpins.config import config

    monkeypatch.setattr(config, "vault_path", lambda: tmp_path / "vault")
    monkeypatch.setattr(library, "schedule_document_memory_indexing", lambda memories: None)
    client = TestClient(app)
    password = secrets.token_urlsafe(24)
    email = "attachment-verification@example.invalid"
    assert client.post("/v1/auth/register", json={"email": email, "password": password}).status_code == 200
    tokens = client.post("/v1/auth/login", json={"identifier": email, "password": password}).json()
    headers = {"Authorization": "Bearer " + tokens["access_token"]}
    client.post("/v1/legal/acceptances", headers=headers, json={"document": "ai_disclosure", "version": "2026-07-13"})
    uploaded = client.post(
        "/v1/uploads",
        headers=headers,
        json={
            "filename": "original.bin",
            "destination": "library",
            "content_base64": base64.b64encode(content).decode(),
        },
    )
    assert uploaded.status_code == 200
    from thoughtpins.db import StoredAttachment
    from thoughtpins.store import get_session

    reference = uploaded.json()["attachment_ref"]
    manifest = client.get("/v1/export", headers=headers).json()["tables"]["stored_attachments"]
    assert len(manifest) == 1 and manifest[0]["reference"] == reference
    assert "payload" not in manifest[0]
    with get_session() as session:
        assert session.query(StoredAttachment).filter(StoredAttachment.reference == reference).count() == 1
    import io
    import zipfile

    exported = client.get("/v1/export/vault/download", headers=headers)
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        originals = [name for name in archive.namelist() if name.startswith("Attachments/") and not name.endswith("/")]
        assert len(originals) == 1
        assert originals[0] == manifest[0]["vault_export_path"]
        assert archive.read(originals[0]) == content
    deleted = client.request("DELETE", "/v1/me", headers=headers, json={"confirm": "DELETE"})
    assert deleted.status_code == 200
    with get_session() as session:
        assert session.query(StoredAttachment).filter(StoredAttachment.reference == reference).count() == 0


def test_deletion_does_not_report_success_when_original_cannot_be_removed(isolated_db, monkeypatch):
    from thoughtpins.data_lifecycle import DataDeletionUnavailable, delete_user_data
    from thoughtpins.store import get_session
    from thoughtpins.users import register_user

    def unavailable(_user_id):
        raise PermissionError("fixture")

    monkeypatch.setattr("thoughtpins.media.attachments.purge_attachments", unavailable)
    with get_session() as session:
        user = register_user(email="delete-failure@example.invalid", session=session, bypass_system_lock=True)
        session.commit()
        with pytest.raises(DataDeletionUnavailable, match="Original upload"):
            delete_user_data(session, user.id)
        session.rollback()
        session.refresh(user)
        assert user.is_active


def test_original_encryption_and_wrong_key_fail_closed(isolated_db, monkeypatch, tmp_path):
    from cryptography.fernet import Fernet

    from thoughtpins.config import config
    from thoughtpins.db import StoredAttachment
    from thoughtpins.media.attachments import export_attachments, save_media_attachment
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user

    monkeypatch.setattr(config, "DATA_ENCRYPTION_KEY", Fernet.generate_key().decode())
    with get_session() as session:
        owner = get_or_create_default_user(session=session).id
    content = b"An invented original that must not appear in stored bytes."
    save_media_attachment(content, user_id=owner, category="document", filename="fixture.txt")
    with get_session() as session:
        assert content not in session.query(StoredAttachment).one().payload
    monkeypatch.setattr(config, "DATA_ENCRYPTION_KEY", Fernet.generate_key().decode())
    with pytest.raises(RuntimeError, match="decryption"):
        export_attachments(owner, tmp_path / "export")
    assert not list((tmp_path / "export").iterdir())
