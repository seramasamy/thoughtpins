from __future__ import annotations

import base64

from thoughtpins.media import extraction as media_extraction


def _b64(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


def test_upload_text_file_to_library_creates_source(isolated_db, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from thoughtpins import library
    from thoughtpins.api import app
    from thoughtpins.config import config
    from thoughtpins.db import DocumentSource
    from thoughtpins.store import get_session

    monkeypatch.setattr(library, "_index_document_memories", lambda memories: None)
    monkeypatch.setattr(library, "schedule_document_memory_indexing", lambda memories: None)
    monkeypatch.setattr(media_extraction.config, "vault_path", lambda: tmp_path / "vault")
    monkeypatch.setattr(config, "vault_path", lambda: tmp_path / "vault")

    client = TestClient(app)
    response = client.post(
        "/v1/uploads",
        json={
            "filename": "orchard-protocol.txt",
            "media_type": "text/plain",
            "destination": "library",
            "title": "Uploaded Orchard Protocol",
            "source_type": "article",
            "content_base64": _b64(b"The uploaded source says the silver orchard marker proves file upload recall."),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route_type"] == "library_upload"
    assert body["document_id"]
    assert body["attachment_saved"] is True
    assert body["attachment_ref"].startswith("09_Attachments/")
    assert body["extracted_chars"] > 20

    session = get_session()
    try:
        doc = session.query(DocumentSource).filter(DocumentSource.id == body["document_id"]).one()
        assert doc.title == "Uploaded Orchard Protocol"
        assert doc.access_method == "user_upload"
        assert doc.rights_basis == "user_provided"
        assert doc.metadata_json["upload"]["filename"] == "orchard-protocol.txt"
    finally:
        session.close()


def test_upload_pdf_uses_shared_extraction_contract(isolated_db, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from thoughtpins import library, uploads
    from thoughtpins.api import app
    from thoughtpins.media import MediaExtraction

    monkeypatch.setattr(library, "_index_document_memories", lambda memories: None)
    monkeypatch.setattr(library, "schedule_document_memory_indexing", lambda memories: None)
    monkeypatch.setattr(media_extraction.config, "vault_path", lambda: tmp_path / "vault")
    monkeypatch.setattr(
        uploads,
        "extract_document_text",
        lambda content, suffix: MediaExtraction(
            text="PDF upload text mentions the blue margin ritual and document recall.",
            kind="document",
            metadata={"suffix": suffix, "engine": "pypdf"},
        ),
    )

    response = TestClient(app).post(
        "/v1/uploads",
        json={
            "filename": "blue-margin.pdf",
            "media_type": "application/pdf",
            "destination": "library",
            "source_type": "paper",
            "content_base64": _b64(b"%PDF fake fixture"),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["media_kind"] == "document"
    assert body["route_type"] == "library_upload"
    assert body["metadata"]["extraction"]["engine"] == "pypdf"
    assert body["document_id"]


def test_upload_journal_destination_uses_chat_ingestion_contract(isolated_db, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from thoughtpins import uploads
    from thoughtpins.api import app
    from thoughtpins.chat.engine import ChatEngineResult

    monkeypatch.setattr(media_extraction.config, "vault_path", lambda: tmp_path / "vault")

    captured: dict[str, str] = {}

    def fake_execute(session, text, **kwargs):
        captured["text"] = text
        captured["surface"] = kwargs.get("surface", "")
        captured["conversation_id"] = kwargs.get("conversation_id", "")
        return ChatEngineResult(status="ok", route_type="journal_entry", reply="Saved.", entry_id="entry_upload_test")

    monkeypatch.setattr(uploads, "execute_chat_message", fake_execute)

    response = TestClient(app).post(
        "/v1/uploads",
        json={
            "filename": "voice-transcript.txt",
            "destination": "journal",
            "caption": "Voice note transcript",
            "content_base64": _b64(b"Today I met Maya at Koyo and discussed upload acceptance tests."),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route_type"] == "journal_upload"
    assert body["entry_id"] == "entry_upload_test"
    assert captured["text"].startswith("journal: Voice note transcript")
    assert captured["surface"] == "upload"


def test_upload_unsupported_binary_needs_text_without_crashing(isolated_db, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from thoughtpins.api import app

    monkeypatch.setattr(media_extraction.config, "vault_path", lambda: tmp_path / "vault")

    response = TestClient(app).post(
        "/v1/uploads",
        json={
            "filename": "archive.bin",
            "media_type": "application/octet-stream",
            "content_base64": _b64(bytes([0, 1, 2, 3, 4, 5]) * 80),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_text"
    assert body["attachment_saved"] is True
    assert body["document_id"] is None
    assert "Paste the text" in body["error"]


def test_upload_empty_and_invalid_base64_are_rejected(isolated_db):
    from fastapi.testclient import TestClient

    from thoughtpins.api import app

    client = TestClient(app)
    empty = client.post("/v1/uploads", json={"filename": "empty.txt", "content_base64": ""})
    invalid = client.post("/v1/uploads", json={"filename": "bad.txt", "content_base64": "not valid base64"})

    assert empty.status_code == 400
    assert "empty" in empty.json()["error"]["message"].lower()
    assert invalid.status_code == 400
    assert "base64" in invalid.json()["error"]["message"].lower()
