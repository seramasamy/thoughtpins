"""Browsing older sources must preserve tenant boundaries and literal search."""

from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient


def test_library_paging_search_and_tenant_isolation(isolated_db):
    from thoughtpins.api import app
    from thoughtpins.db import DocumentSource, RawEntry
    from thoughtpins.library import list_documents
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram

    client = TestClient(app)
    owner_id = client.get("/v1/me").json()["id"]
    with get_session() as session:
        other = get_or_create_user_for_telegram("catalog-other", session=session)
        for user_id in (owner_id, other.id):
            raw = RawEntry(user_id=user_id, raw_text="Synthetic catalog fixture", content_hash=user_id)
            session.add(raw)
            session.flush()
            for number in range(105 if user_id == owner_id else 1):
                session.add(
                    DocumentSource(
                        user_id=user_id,
                        raw_entry_id=raw.id,
                        title="Archive 10%_complete" if number == 0 else f"Source {number:03}",
                        author="Violet Compass" if number == 0 else None,
                        source_domain="fixture.invalid",
                        content_hash=f"{user_id}-{number}",
                        raw_text="Synthetic source",
                        created_at_utc=datetime(2026, 1, 1),
                        id=f"{user_id[:24]}{number:08}",
                    )
                )
        session.commit()
        assert len(list_documents(session, other.id, limit=100)) == 1

    first = client.get("/v1/library", params={"limit": 100}).json()
    second = client.get("/v1/library", params={"limit": 100, "offset": 100}).json()
    assert len(first) == 100 and len(second) == 5
    ids = [source["id"] for source in first + second]
    assert len(set(ids)) == 105
    assert ids == sorted(ids, reverse=True)  # Equal dates have a stable tie-breaker.
    assert first == client.get("/v1/library", params={"limit": 100}).json()
    for query in ("10%_", "violet COMPASS"):
        response = client.get("/v1/library", params={"q": query})
        assert response.status_code == 200
        assert [source["title"] for source in response.json()] == ["Archive 10%_complete"]
    assert client.get("/v1/library", params={"q": "10%_absent"}).json() == []
    assert len(client.get("/v1/library", params={"q": "FIXTURE.INVALID"}).json()) == 20
    assert client.get("/v1/library", params={"offset": -1}).status_code == 422
    assert client.get("/v1/library", params={"q": "x" * 501}).status_code == 422
