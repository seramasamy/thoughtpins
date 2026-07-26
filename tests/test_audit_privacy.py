from __future__ import annotations

import json

from thoughtpins.audit import _safe_metadata, record_audit_event
from thoughtpins.db import AuditLog, User
from thoughtpins.privacy import fingerprint_identifier
from thoughtpins.store import get_session


def test_safe_metadata_recursively_removes_sensitive_values_and_fingerprints_ips():
    metadata = {
        "ip": "203.0.113.7",
        "authorization": "Bearer secret-token",
        "raw_text": "today I wrote a private journal entry",
        "conversation_key": "main",
        "fields": ["timezone", "preferred_name"],
        "nested": {
            "client_ip": "198.51.100.2",
            "token_hash": "abc123",
            "safe": "ok",
            "content_hash": "internal-content-hash",
        },
        "items": [
            {"password": "pw", "platform": "ios"},
            {"remote_addr": "192.0.2.44", "message": "private chat"},
        ],
    }

    safe = _safe_metadata(metadata)
    serialized = json.dumps(safe, sort_keys=True)

    assert safe["ip_hash"] == fingerprint_identifier("203.0.113.7")
    assert safe["conversation_key"] == "main"
    assert safe["fields"] == ["timezone", "preferred_name"]
    assert safe["nested"]["client_ip_hash"] == fingerprint_identifier("198.51.100.2")
    assert safe["nested"]["safe"] == "ok"
    assert safe["items"][0] == {"platform": "ios"}
    assert safe["items"][1]["remote_addr_hash"] == fingerprint_identifier("192.0.2.44")

    assert "203.0.113.7" not in serialized
    assert "198.51.100.2" not in serialized
    assert "192.0.2.44" not in serialized
    assert "secret-token" not in serialized
    assert "private journal" not in serialized
    assert "private chat" not in serialized
    assert "abc123" not in serialized
    assert "internal-content-hash" not in serialized


def test_record_audit_event_persists_sanitized_metadata(isolated_db):
    session = get_session()
    try:
        user = User(email="audit-privacy@example.local", display_name="Audit Privacy")
        session.add(user)
        session.commit()

        record_audit_event(
            session,
            user_id=user.id,
            action="auth.login",
            metadata={
                "method": "password",
                "identifier": "email",
                "ip": "203.0.113.9",
                "nested": {"access_token": "secret", "client_ip": "198.51.100.9"},
            },
        )

        row = session.query(AuditLog).filter(AuditLog.user_id == user.id).one()
        metadata = row.metadata_json
        serialized = json.dumps(metadata, sort_keys=True)

        assert metadata["method"] == "password"
        assert metadata["identifier"] == "email"
        assert metadata["ip_hash"] == fingerprint_identifier("203.0.113.9")
        assert metadata["nested"]["client_ip_hash"] == fingerprint_identifier("198.51.100.9")
        assert "203.0.113.9" not in serialized
        assert "198.51.100.9" not in serialized
        assert "secret" not in serialized
    finally:
        session.close()
