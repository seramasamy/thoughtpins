"""Account deletion must actually purge. The privacy policy is a legal promise.

Written the way the claim would be audited rather than the way the code is
organised: create an account, give it real content through the public API,
delete it, then walk **every table in the schema** and assert that no row
anywhere is still owned by that user. A new table added next year with a
`user_id` column and no entry in the deletion list fails this test the day it
appears, which is the failure mode a hand-written list of tables cannot catch.

What deliberately survives is the user row itself, anonymised: a tombstone so
the identifier cannot be reused and so a deletion can be shown to have
happened. Everything on it that came from the person is cleared, and that is
asserted field by field.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

PASSPHRASE = "correct horse battery staple"
JOURNAL_TEXT = "I met Priya at the Harbour Market and we discussed the Northstar project."


@pytest.fixture
def client(isolated_db):
    from thoughtpins.api import app

    return TestClient(app)


def _make_account_with_content(client: TestClient) -> tuple[str, dict[str, str]]:
    email = "purge-target@thoughtpins.com"
    assert client.post("/v1/auth/register", json={"email": email, "password": PASSPHRASE}).status_code == 200
    tokens = client.post("/v1/auth/login", json={"identifier": email, "password": PASSPHRASE}).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    client.post(
        "/v1/legal/acceptances",
        headers=headers,
        json={"document": "ai_disclosure", "version": "2026-07-13"},
    )
    assert client.post("/v1/entries", headers=headers, json={"text": JOURNAL_TEXT}).status_code == 200
    client.post("/v1/chat", headers=headers, json={"text": "what about Priya?", "surface": "ios"})
    me = client.get("/v1/me", headers=headers).json()
    return me.get("user_id") or me["id"], headers


def _owned_row_counts(user_id: str) -> dict[str, int]:
    """Every table with an owner column, and how many rows this user still has."""
    from thoughtpins.store import get_session

    counts: dict[str, int] = {}
    with get_session() as session:
        inspector = inspect(session.get_bind())
        for table in inspector.get_table_names():
            columns = {column["name"] for column in inspector.get_columns(table)}
            owner = next((c for c in ("user_id", "owner_id", "account_id") if c in columns), None)
            if owner is None:
                continue
            found = session.execute(
                text(f'SELECT COUNT(*) FROM "{table}" WHERE {owner} = :uid'), {"uid": user_id}
            ).scalar_one()
            if found:
                counts[table] = int(found)
    return counts


def test_deleting_an_account_leaves_no_row_owned_by_it_anywhere(client):
    user_id, headers = _make_account_with_content(client)

    before = _owned_row_counts(user_id)
    assert before, "the account had no content, so this test would prove nothing"

    response = client.request("DELETE", "/v1/me", headers=headers, json={"confirm": "DELETE"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "deleted"

    after = _owned_row_counts(user_id)
    assert after == {}, f"rows survived deletion: {after} (before: {before})"


def test_the_journal_text_itself_is_gone_from_every_column(client):
    """Not just unowned -- gone.

    Row counts by owner would miss a row whose user_id was nulled instead of
    deleted, which would leave the journal text sitting in the database with no
    owner. This searches for the text itself.
    """
    _, headers = _make_account_with_content(client)
    client.request("DELETE", "/v1/me", headers=headers, json={"confirm": "DELETE"})

    from thoughtpins.store import get_session

    survivors: list[str] = []
    with get_session() as session:
        inspector = inspect(session.get_bind())
        for table in inspector.get_table_names():
            for column in inspector.get_columns(table):
                name = column["name"]
                try:
                    found = session.execute(
                        text(f'SELECT COUNT(*) FROM "{table}" WHERE CAST("{name}" AS TEXT) LIKE :needle'),
                        {"needle": "%Harbour Market%"},
                    ).scalar_one()
                except Exception:
                    continue
                if found:
                    survivors.append(f"{table}.{name} ({found})")
    assert not survivors, f"journal text survived deletion in: {survivors}"


def test_the_tombstone_keeps_nothing_that_came_from_the_person(client):
    user_id, headers = _make_account_with_content(client)
    client.request("DELETE", "/v1/me", headers=headers, json={"confirm": "DELETE"})

    from thoughtpins.db import User
    from thoughtpins.store import get_session

    with get_session() as session:
        user = session.get(User, user_id)
        assert user is not None, "the tombstone row should remain so the id cannot be reused"
        assert user.is_active is False
        assert user.deleted_at_utc is not None
        assert user.email is None
        assert user.phone is None
        assert user.password_hash is None
        assert user.telegram_chat_id is None
        assert user.display_name == "Deleted User"
        assert user.api_key == f"deleted_{user_id}"
        # This one survived a real deletion until it was found: it still held
        # the AI-disclosure acceptance and the account's settings.
        assert user.preferences_json is None, "settings survived deletion"


def test_the_deleted_session_no_longer_works(client):
    _, headers = _make_account_with_content(client)
    client.request("DELETE", "/v1/me", headers=headers, json={"confirm": "DELETE"})
    assert client.get("/v1/me", headers=headers).status_code in (401, 403)


# ----------------------------------------------------------- the filesystem
#
# The table sweep above cannot see disk. Five stores held user content outside
# the database and every one of them survived deletion until it was looked
# for: generated report files, the vault projection and its export zip, graph
# visual exports, staged vault-import archives, and the Telegram conversation
# cache. Magic-link tokens are the sixth store: rows keyed by email, invisible
# to a user_id purge.


@pytest.fixture
def scratch_paths(monkeypatch, tmp_path):
    from thoughtpins.config import config

    config_cls = type(config)
    for key, value in (
        ("VAULT_PATH", tmp_path / "vault"),
        ("REPORTS_PATH", tmp_path / "reports"),
        ("CONVERSATION_CACHE_PATH", tmp_path / "conversation_cache.json"),
    ):
        monkeypatch.setattr(config, key, value)
        monkeypatch.setattr(config_cls, key, value)
    return tmp_path


def test_deletion_purges_every_store_outside_the_database(client, scratch_paths):
    from thoughtpins.chat import conversation_state
    from thoughtpins.config import config
    from thoughtpins.db import User, VaultImportSession
    from thoughtpins.db_platform import MagicLinkToken
    from thoughtpins.store import get_session

    user_id, headers = _make_account_with_content(client)
    email = "purge-target@thoughtpins.com"
    chat_id = "8675309"

    # Seed each store the way production writes it.
    reports_dir = config.reports_path() / user_id
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_file = reports_dir / "weekly.md"
    report_file.write_text("# A report containing journal content", encoding="utf-8")

    vault_dir = config.vault_path() / user_id
    (vault_dir / "Journal").mkdir(parents=True, exist_ok=True)
    (vault_dir / "Journal" / "2026-08-29.md").write_text(JOURNAL_TEXT, encoding="utf-8")
    vault_zip = config.vault_path() / f"{user_id}.zip"
    vault_zip.write_bytes(b"PK\x05\x06" + b"\x00" * 18)

    graph_dir = config.vault_path() / "_system" / "graph_exports" / user_id
    graph_dir.mkdir(parents=True, exist_ok=True)
    (graph_dir / "memory_graph.html").write_text("<html>graph</html>", encoding="utf-8")

    archive_dir = config.resolve_path(config.VAULT_IMPORT_PATH)
    archive_dir.mkdir(parents=True, exist_ok=True)
    staged_archive = archive_dir / "abababababababababababababababab.zip.part"
    staged_archive.write_bytes(b"half an uploaded vault")

    with get_session() as session:
        session.add(
            VaultImportSession(
                user_id=user_id,
                filename="my-vault.zip",
                storage_key="abababababababababababababababab",
                status="uploading",
                expected_bytes=1024,
                expires_at_utc=_far_future(),
            )
        )
        session.add(MagicLinkToken(email=email, token_hash="probe-hash", expires_at_utc=_far_future()))
        session.query(User).filter(User.id == user_id).update({"telegram_chat_id": chat_id})
        session.commit()

    conversation_state.forget_conversation("warmup-nonexistent")  # ensure module loads cleanly
    cache = {chat_id: [{"role": "user", "content": JOURNAL_TEXT}]}
    conversation_state.save_conversation_cache(cache)

    response = client.request("DELETE", "/v1/me", headers=headers, json={"confirm": "DELETE"})
    assert response.status_code == 200, response.text

    assert not report_file.exists(), "the generated report file survived deletion"
    assert not reports_dir.exists(), "the per-user reports directory survived deletion"
    assert not vault_dir.exists(), "the vault projection survived deletion"
    assert not vault_zip.exists(), "the vault export zip survived deletion"
    assert not graph_dir.exists(), "the graph exports directory survived deletion"
    assert not staged_archive.exists(), "the staged vault-import archive survived deletion"

    with get_session() as session:
        assert session.query(VaultImportSession).filter(VaultImportSession.user_id == user_id).count() == 0
        assert session.query(MagicLinkToken).filter(MagicLinkToken.email == email).count() == 0

    fresh: dict = {}
    conversation_state.load_conversation_cache(fresh)
    assert chat_id not in fresh, "the Telegram conversation cache still holds the deleted user's turns"


def _far_future():
    from datetime import datetime, timedelta

    return datetime.utcnow() + timedelta(hours=1)
