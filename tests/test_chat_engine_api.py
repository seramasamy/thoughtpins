from __future__ import annotations

from fastapi.testclient import TestClient


def test_chat_endpoint_replies_and_persists_style_memory(isolated_db, monkeypatch):
    from thoughtpins.api import app
    from thoughtpins.bot import commands
    from thoughtpins.db import RawEntry, User
    from thoughtpins.store import get_session

    class FakeLlm:
        def chat(self, messages: list[dict], temperature: float, max_tokens: int) -> str:
            assert "USER STYLE MEMORY" in messages[0]["content"]
            assert "Friendly & Professional" in messages[0]["content"]
            assert "Casual markers the user uses" not in messages[0]["content"]
            return "Keep in mind this is a demo excerpt, bro - not a complete tally."

    monkeypatch.setattr(commands, "get_llm_client", lambda: FakeLlm())

    client = TestClient(app)
    response = client.post(
        "/v1/chat",
        json={"text": "yo bro whats up", "surface": "web", "conversation_id": "main"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "replied"
    assert body["route_type"] == "chat"
    assert body["reply"] == "Keep in mind this is a demo excerpt - not a complete tally."

    session = get_session()
    try:
        user = session.query(User).one()
        entry = session.query(RawEntry).filter(RawEntry.user_id == user.id).one()
        assert entry.source == "web_chat"
        assert entry.processed_status == "conversation"
        assert entry.telegram_chat_id == "web:main"
        assert entry.raw_text == "yo bro whats up"
        assert "bro" in user.preferences_json["style_profile"]["casual_marker_counts"]
    finally:
        session.close()


def test_chat_endpoint_only_mirrors_direct_address_when_explicitly_selected(isolated_db, monkeypatch):
    from thoughtpins.api import app
    from thoughtpins.bot import commands

    class FakeLlm:
        def chat(self, messages: list[dict], temperature: float, max_tokens: int) -> str:
            assert "Match My Style" in messages[0]["content"]
            assert "Casual markers the user uses: yo, bro" in messages[0]["content"]
            return "Got it, bro."

    monkeypatch.setattr(commands, "get_llm_client", lambda: FakeLlm())
    client = TestClient(app)
    updated = client.patch("/v1/preferences", json={"response_style": "mirror"})
    assert updated.status_code == 200

    response = client.post(
        "/v1/chat",
        json={"text": "yo bro whats up", "surface": "web", "conversation_id": "main"},
    )

    assert response.status_code == 200
    assert response.json()["reply"] == "Got it, bro."


def test_chat_endpoint_can_force_journal_save(isolated_db, monkeypatch):
    from thoughtpins.api import app
    from thoughtpins.db import RawEntry
    from thoughtpins.utils import hash_text, local_now, utcnow

    def fake_process_message(session, text, **kwargs):
        assert text == "today I met Maya at Koyo"
        assert kwargs["source"] == "web_chat"
        assert kwargs["telegram_chat_id"] == "web:main"
        now_local = local_now()
        session.add(
            RawEntry(
                id="entry-chat-1",
                user_id=kwargs["user_id"],
                created_at_utc=utcnow(),
                local_date=now_local.date(),
                local_time=now_local.strftime("%H:%M"),
                source=kwargs["source"],
                telegram_chat_id=kwargs["telegram_chat_id"],
                raw_text=text,
                content_hash=hash_text(text),
                processed_status="completed",
            )
        )
        session.flush()
        return {
            "type": "journal_stored",
            "entry_id": "entry-chat-1",
            "stats": {"entities": 1, "events": 1, "memories": 2, "relationships": 0},
        }

    monkeypatch.setattr("thoughtpins.chat.engine.process_message", fake_process_message)

    client = TestClient(app)
    response = client.post(
        "/v1/chat",
        json={"text": "journal: today I met Maya at Koyo", "surface": "web", "conversation_id": "main"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["route_type"] == "journal_entry"
    assert body["entry_id"] == "entry-chat-1"
    assert "Captured: 2 memories, 1 entity, 1 event." in body["reply"]


def test_chat_endpoint_returns_confirmation_for_risky_natural_command(isolated_db):
    from thoughtpins.api import app

    client = TestClient(app)
    response = client.post(
        "/v1/chat",
        json={"text": "undo that", "surface": "web", "conversation_id": "main"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "confirmation_required"
    assert body["requires_confirmation"] is True
    assert "confirm undo" in body["confirmation_prompt"]
    assert body["metadata"]["pending_action_id"]


def test_chat_endpoint_persists_conversation_and_messages(isolated_db, monkeypatch):
    from thoughtpins.api import app
    from thoughtpins.bot import commands

    class FakeLlm:
        def chat(self, messages: list[dict], temperature: float, max_tokens: int) -> str:
            return "I can work with that memory."

    monkeypatch.setattr(commands, "get_llm_client", lambda: FakeLlm())

    client = TestClient(app)
    response = client.post(
        "/v1/chat",
        json={"text": "hey can you remember what I said about Koyo?", "surface": "web", "conversation_id": "main"},
    )

    assert response.status_code == 200
    conversation_id = response.json()["metadata"]["conversation_db_id"]

    conversations = client.get("/v1/chat/conversations?surface=web")
    assert conversations.status_code == 200
    assert conversations.json()["items"][0]["id"] == conversation_id
    assert conversations.json()["items"][0]["conversation_key"] == "web:main"

    messages = client.get(f"/v1/chat/conversations/{conversation_id}/messages")
    assert messages.status_code == 200
    items = messages.json()["items"]
    assert [item["role"] for item in items] == ["user", "assistant"]
    assert items[0]["text"] == "hey can you remember what I said about Koyo?"
    assert items[1]["text"] == "I can work with that memory."


def test_chat_pending_action_can_be_confirmed_durably(isolated_db):
    from thoughtpins.api import app
    from thoughtpins.db import RawEntry
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user
    from thoughtpins.utils import hash_text, local_now, utcnow

    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        now_local = local_now()
        entry = RawEntry(
            user_id=user.id,
            created_at_utc=utcnow(),
            local_date=now_local.date(),
            local_time=now_local.strftime("%H:%M"),
            source="web_chat",
            telegram_chat_id="web:main",
            raw_text="today I wrote the launch memo",
            content_hash=hash_text("undo-test-launch-memo"),
            processed_status="completed",
        )
        session.add(entry)
        session.commit()
        entry_id = entry.id
    finally:
        session.close()

    client = TestClient(app)
    pending_response = client.post(
        "/v1/chat",
        json={"text": "undo that", "surface": "web", "conversation_id": "main"},
    )
    assert pending_response.status_code == 200
    pending_id = pending_response.json()["metadata"]["pending_action_id"]

    confirm_response = client.post(
        "/v1/chat",
        json={
            "text": "confirm",
            "surface": "web",
            "conversation_id": "main",
            "pending_action_id": pending_id,
            "confirm_action": True,
        },
    )
    assert confirm_response.status_code == 200
    body = confirm_response.json()
    assert body["status"] == "undone"
    assert body["metadata"]["entry_id"] == entry_id

    session = get_session()
    try:
        assert session.get(RawEntry, entry_id) is None
    finally:
        session.close()


def test_chat_endpoint_runs_natural_doctor_and_audit(isolated_db, monkeypatch):
    from thoughtpins.api import app
    from thoughtpins.founder import ops as founder_ops
    from thoughtpins.memory import audit as memory_audit

    def fake_doctor(session, *, user_id: str, chat_id: str):
        assert user_id
        assert chat_id == "web:main"
        return "Thought Pins Doctor\nOK database: reachable", True

    class FakeAudit:
        pass

    monkeypatch.setattr(founder_ops, "build_doctor_report", fake_doctor)
    monkeypatch.setattr(memory_audit, "audit_memory_system", lambda session, *, user_id: FakeAudit())
    monkeypatch.setattr(memory_audit, "format_audit_report", lambda report: "Memory Audit\nGrade: A+")

    client = TestClient(app)
    doctor = client.post(
        "/v1/chat",
        json={"text": "run a health check", "surface": "web", "conversation_id": "main"},
    )
    assert doctor.status_code == 200
    doctor_body = doctor.json()
    assert doctor_body["route_type"] == "natural_command"
    assert doctor_body["metadata"]["natural_action"] == "doctor"
    assert doctor_body["metadata"]["doctor_ok"] is True
    assert "Thought Pins Doctor" in doctor_body["reply"]

    audit = client.post(
        "/v1/chat",
        json={"text": "audit my memory system", "surface": "web", "conversation_id": "main"},
    )
    assert audit.status_code == 200
    audit_body = audit.json()
    assert audit_body["route_type"] == "natural_command"
    assert audit_body["metadata"]["natural_action"] == "audit"
    assert "Memory Audit" in audit_body["reply"]


def test_chat_endpoint_runs_source_and_context_diagnostics_naturally(isolated_db, monkeypatch):
    from datetime import datetime, timezone

    from thoughtpins.api import app
    from thoughtpins.bot import commands
    from thoughtpins.db import DocumentChunk, DocumentSource, RawEntry
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user
    from thoughtpins.utils import hash_text

    monkeypatch.setattr(
        commands,
        "describe_memory_context_package",
        lambda *args, **kwargs: {
            "configured_mode": "smart",
            "effective_mode": "smart",
            "forced_full": False,
            "include_private": False,
            "active_chars": 1200,
            "prompt_budget_chars": 10000,
            "nav_map_chars": 300,
            "full_context_chars": 5000,
            "full_inline_threshold_chars": 20000,
            "full_context_inline": False,
            "vault_inline": False,
            "sections": [{"title": "QUERY-RELEVANT MEMORY", "chars": 700}],
        },
    )

    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        raw = RawEntry(
            user_id=user.id,
            created_at_utc=now,
            local_date=now.date(),
            local_time="12:00",
            source="test",
            raw_text="Source fixture.",
            content_hash=hash_text("source fixture"),
            processed_status="processed",
        )
        session.add(raw)
        session.flush()
        doc = DocumentSource(
            user_id=user.id,
            raw_entry_id=raw.id,
            source_type="text",
            title="Memory Systems Essay",
            content_hash=hash_text("memory systems essay"),
            raw_text="A source about memory systems.",
            summary="A short summary about memory systems.",
            status="processed",
            local_date=now.date(),
            access_method="user_paste",
            rights_basis="user_provided",
        )
        session.add(doc)
        session.flush()
        session.add(
            DocumentChunk(
                user_id=user.id,
                document_id=doc.id,
                chunk_index=0,
                text="First source excerpt about retrieval diagnostics.",
            )
        )
        session.commit()
    finally:
        session.close()

    client = TestClient(app)
    source = client.post(
        "/v1/chat",
        json={"text": "show source Memory Systems Essay", "surface": "web", "conversation_id": "main"},
    )
    assert source.status_code == 200
    assert "Source: Memory Systems Essay" in source.json()["reply"]
    assert "retrieval diagnostics" in source.json()["reply"]

    context = client.post(
        "/v1/chat",
        json={
            "text": "show context diagnostics for retrieval diagnostics",
            "surface": "web",
            "conversation_id": "main",
        },
    )
    assert context.status_code == 200
    assert "Context diagnostics" in context.json()["reply"]
    assert "QUERY-RELEVANT MEMORY" in context.json()["reply"]


def test_chat_endpoint_returns_ambiguity_route_hint(isolated_db, monkeypatch):
    from thoughtpins.api import app
    from thoughtpins.bot import commands

    class FakeLlm:
        def chat(self, messages: list[dict], temperature: float, max_tokens: int) -> str:
            return "yeah, let's talk through that thought."

    monkeypatch.setattr(commands, "get_llm_client", lambda: FakeLlm())

    client = TestClient(app)
    response = client.post(
        "/v1/chat",
        json={"text": "I think memory is mostly attention", "surface": "web", "conversation_id": "main"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route_type"] == "chat"
    assert body["metadata"]["classification"]["type"] == "ambiguous"
    assert "Replying as chat" in body["metadata"]["routing_hint"]


def test_chat_endpoint_natural_mark_that_as_chat_demotes_latest_save(isolated_db):
    from datetime import datetime, timezone

    from thoughtpins.api import app
    from thoughtpins.bot.style_memory import CHAT_STATUS
    from thoughtpins.db import RawEntry
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user
    from thoughtpins.utils import hash_text

    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        entry = RawEntry(
            user_id=user.id,
            created_at_utc=now,
            local_date=now.date(),
            local_time="12:30",
            source="web_chat",
            telegram_chat_id="web:main",
            raw_text="I think this might have been too casual to save as journal.",
            content_hash=hash_text("mark-chat-fixture"),
            processed_status="completed",
        )
        session.add(entry)
        session.commit()
        entry_id = entry.id
    finally:
        session.close()

    client = TestClient(app)
    response = client.post(
        "/v1/chat",
        json={"text": "that was just chat", "surface": "web", "conversation_id": "main"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "marked_chat"
    assert body["metadata"]["entry_id"] == entry_id

    session = get_session()
    try:
        entry = session.get(RawEntry, entry_id)
        assert entry is not None
        assert entry.processed_status == CHAT_STATUS
    finally:
        session.close()
