from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient


def _entry(*, user_id: str, text: str, importance: int | None = None, chat_id: str = ""):
    from thoughtpins.db import RawEntry
    from thoughtpins.utils import hash_text, local_today

    return RawEntry(
        user_id=user_id,
        created_at_utc=datetime.now(),
        local_date=local_today(),
        source="web_chat",
        telegram_chat_id=chat_id,
        raw_text=text,
        content_hash=hash_text(f"{user_id}:{text}"),
        processed_status="completed",
        user_importance=importance,
        importance_source="test" if importance is not None else None,
    )


def test_importance_validation_and_bounded_retrieval_prior():
    from thoughtpins.importance import importance_bonus, normalize_user_importance

    assert normalize_user_importance(None) is None
    assert normalize_user_importance("clear") is None
    assert normalize_user_importance("5") == 5
    assert importance_bonus(1) == -0.01
    assert importance_bonus(5) == 0.06
    assert importance_bonus(None) == 0.0
    for invalid in (True, 0, 6, "high"):
        with pytest.raises(ValueError):
            normalize_user_importance(invalid)


def test_importance_update_is_owned_audited_clearable_and_reversible(isolated_db):
    from thoughtpins.db import AuditLog, RawEntry
    from thoughtpins.importance import set_entry_importance, undo_latest_importance
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user, register_user

    session = get_session()
    try:
        owner = get_or_create_default_user(session=session)
        other = register_user(email="importance-other@example.com", session=session)
        entry = _entry(user_id=owner.id, text="A personally meaningful turning point.", chat_id="web:main")
        session.add(entry)
        session.commit()

        assert set_entry_importance(session, user_id=other.id, entry_id=entry.id, value=5, source="api") is None

        update = set_entry_importance(
            session,
            user_id=owner.id,
            entry_id=entry.id,
            value=5,
            source="api",
            conversation_key="web:main",
        )
        session.commit()
        assert update is not None and update.changed is True
        assert session.query(RawEntry).filter_by(id=entry.id).one().user_importance == 5
        assert session.query(AuditLog).filter_by(action="entry.importance.updated").count() == 1

        undone = undo_latest_importance(session, user_id=owner.id, conversation_key="web:main")
        session.commit()
        assert undone is not None and undone.user_importance is None
        assert session.query(RawEntry).filter_by(id=entry.id).one().user_importance is None

        cleared = set_entry_importance(session, user_id=owner.id, entry_id=entry.id, value=None)
        assert cleared is not None and cleared.changed is False
    finally:
        session.close()


def test_entry_importance_api_validates_and_enforces_tenant_scope(isolated_db):
    from thoughtpins.api import app
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user, register_user

    session = get_session()
    try:
        owner = get_or_create_default_user(session=session)
        other = register_user(email="importance-api-other@example.com", session=session)
        owned = _entry(user_id=owner.id, text="Owned importance API entry.")
        foreign = _entry(user_id=other.id, text="Foreign importance API entry.")
        session.add_all([owned, foreign])
        session.commit()
        owned_id, foreign_id = owned.id, foreign.id
    finally:
        session.close()

    client = TestClient(app)
    rated = client.patch(f"/v1/entries/{owned_id}/importance", json={"user_importance": 5})
    assert rated.status_code == 200
    assert rated.json()["user_importance"] == 5
    assert rated.json()["importance_source"] == "api"
    assert rated.json()["importance_updated_at"]

    assert client.patch(f"/v1/entries/{owned_id}/importance", json={"user_importance": 0}).status_code == 422
    assert client.patch(f"/v1/entries/{foreign_id}/importance", json={"user_importance": 5}).status_code == 404

    cleared = client.patch(f"/v1/entries/{owned_id}/importance", json={"user_importance": None})
    assert cleared.status_code == 200
    assert cleared.json()["user_importance"] is None


@pytest.mark.parametrize(
    ("text", "action", "args"),
    [
        ("rate that five stars", "set_importance", ["5"]),
        ("set the last entry importance to 4", "set_importance", ["4"]),
        ("clear that rating", "set_importance", ["clear"]),
        ("undo that rating", "undo_importance", []),
        ("ask me to rate important entries", "importance_prompts", ["on"]),
        ("stop asking me to rate entries", "importance_prompts", ["off"]),
    ],
)
def test_natural_importance_commands_are_explicit(text: str, action: str, args: list[str]):
    from thoughtpins.bot.natural_commands import route_natural_command

    route = route_natural_command(text)
    assert route is not None
    assert route.action == action
    assert route.args == args


@pytest.mark.parametrize(
    "text",
    [
        "The restaurant earned five stars for the pasta.",
        "I would rate today as one of the best days this year.",
        "Five stars were visible after sunset.",
    ],
)
def test_natural_importance_parser_does_not_hijack_prose(text: str):
    from thoughtpins.bot.natural_commands import route_natural_command

    assert route_natural_command(text) is None


def test_chat_surface_can_rate_undo_and_configure_prompts_without_commands(isolated_db):
    from thoughtpins.api import app
    from thoughtpins.db import RawEntry, User
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user

    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        entry = _entry(user_id=user.id, text="The saved journal turn.", chat_id="web:main")
        session.add(entry)
        session.commit()
        entry_id = entry.id
        user_id = user.id
    finally:
        session.close()

    client = TestClient(app)
    rated = client.post(
        "/v1/chat",
        json={"text": "rate that five stars", "surface": "web", "conversation_id": "main"},
    )
    assert rated.status_code == 200
    assert rated.json()["status"] == "importance_updated"
    assert rated.json()["metadata"]["user_importance"] == 5

    enabled = client.post(
        "/v1/chat",
        json={
            "text": "ask me to rate important entries",
            "surface": "web",
            "conversation_id": "main",
        },
    )
    assert enabled.status_code == 200
    assert enabled.json()["metadata"]["importance_prompts_enabled"] is True

    undone = client.post(
        "/v1/chat",
        json={"text": "undo that rating", "surface": "web", "conversation_id": "main"},
    )
    assert undone.status_code == 200
    assert undone.json()["status"] == "importance_undone"

    session = get_session()
    try:
        assert session.query(RawEntry).filter_by(id=entry_id).one().user_importance is None
        prefs = session.query(User).filter_by(id=user_id).one().preferences_json
        assert prefs["app_preferences"]["importance_prompts_enabled"] is True
    finally:
        session.close()


def test_importance_is_a_bounded_search_signal_and_recap_order(isolated_db, monkeypatch):
    from thoughtpins.db import Memory
    from thoughtpins.memory import search as search_module
    from thoughtpins.reports.generator import ReportGenerator
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user

    class EmptyVectorStore:
        def search(self, query: str, limit: int = 20, *, user_id: str | None = None):
            return []

    monkeypatch.setattr(search_module, "get_vector_store", lambda: EmptyVectorStore())

    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        low = _entry(user_id=user.id, text="Atlas reliability decision", importance=1)
        high = _entry(user_id=user.id, text="Atlas reliability decision", importance=5)
        session.add_all([low, high])
        session.flush()
        low_memory = Memory(
            user_id=user.id,
            raw_entry_id=low.id,
            memory_type="observation",
            text="Atlas reliability decision low importance evidence.",
            local_date=low.local_date,
        )
        high_memory = Memory(
            user_id=user.id,
            raw_entry_id=high.id,
            memory_type="observation",
            text="Atlas reliability decision high importance evidence.",
            local_date=high.local_date,
        )
        session.add_all([low_memory, high_memory])
        session.commit()

        results = search_module.search("Atlas reliability decision", session=session, user_id=user.id, limit=10)
        assert results[0].source_entry_id == high.id
        assert results[0].ranking_signals["importance_bonus"] == 0.06
        low_result = next(result for result in results if result.source_entry_id == low.id)
        assert low_result.ranking_signals["importance_bonus"] == -0.01

        recap = ReportGenerator(session, user_id=user.id).generate_markdown("daily")
        assert recap.index("high importance evidence") < recap.index("low importance evidence")
        assert "[importance: 5/5]" in recap
    finally:
        session.close()


def test_async_job_passes_importance_to_ingestion(isolated_db, monkeypatch):
    from thoughtpins.db import IngestionJob, RawEntry
    from thoughtpins.jobs import create_ingestion_job, run_ingestion_job
    from thoughtpins.store import get_session
    from thoughtpins.users import register_user

    user = register_user(email="importance-job@example.com")
    session = get_session()
    try:
        job = create_ingestion_job(
            session,
            user_id=user.id,
            text="A queued important memory.",
            metadata={"user_importance": 4},
        )
        job_id = job.id
    finally:
        session.close()

    def fake_process_message(session, text, **kwargs):
        assert kwargs["user_importance"] == 4
        entry = _entry(user_id=user.id, text=text, importance=kwargs["user_importance"])
        session.add(entry)
        session.flush()
        return {"type": "journal_stored", "entry_id": entry.id}

    monkeypatch.setattr("thoughtpins.jobs.process_message", fake_process_message)
    run_ingestion_job(job_id)

    session = get_session()
    try:
        stored_job = session.query(IngestionJob).filter_by(id=job_id).one()
        stored_entry = session.query(RawEntry).filter_by(id=stored_job.entry_id).one()
        assert stored_job.status == "completed"
        assert stored_entry.user_importance == 4
    finally:
        session.close()
