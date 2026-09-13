from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize("surface", ["web", "ios", "android"])
def test_logical_conversation_edit_retires_branch_and_returns_real_message_ids(isolated_db, surface):
    from thoughtpins.api import app
    from thoughtpins.db import ChatMessage
    from thoughtpins.store import get_session

    client = TestClient(app)
    base = {"surface": surface, "conversation_id": "main"}
    # Unknown slash commands are deterministic and still exercise actual chat
    # routing, storage, finalization and the HTTP contract, without a provider.
    first = client.post("/v1/chat", json={**base, "text": "/first-fixture"})
    assert first.status_code == 200
    target = first.json()["user_message_id"]
    assert target
    conversation = first.json()["metadata"]["conversation_db_id"]
    client.post("/v1/chat", json={**base, "text": "/second-fixture"})
    edited = client.post("/v1/chat", json={**base, "text": "/replacement-fixture", "supersedes_message_id": target})
    assert edited.status_code == 200
    body = edited.json()
    assert body["user_message_id"] and body["user_message_id"] != target
    assert len(body["superseded_message_ids"]) == 4
    history = client.get(f"/v1/chat/conversations/{conversation}/messages").json()["items"]
    assert len(history) == 2
    assert history[0]["text"] == "/replacement-fixture"
    with get_session() as session:
        retired = session.get(ChatMessage, target)
        assert retired.superseded_by_message_id == body["user_message_id"]


def test_invalid_edit_never_silently_appends(isolated_db):
    from thoughtpins.api import app

    client = TestClient(app)
    first = client.post("/v1/chat", json={"text": "/fixture", "conversation_id": "main"}).json()
    response = client.post(
        "/v1/chat",
        json={
            "text": "/replacement",
            "conversation_id": "elsewhere",
            "supersedes_message_id": first["user_message_id"],
        },
    )
    assert response.status_code == 422
    assert client.get("/v1/chat/conversations").json()["total"] == 1


def test_failed_edit_keeps_old_history_even_if_an_action_committed(isolated_db, monkeypatch):
    from thoughtpins.api import app
    from thoughtpins.chat import engine
    from thoughtpins.chat.models import ChatRouteDecision

    client = TestClient(app)
    base = {"surface": "web", "conversation_id": "main"}
    first = client.post("/v1/chat", json={**base, "text": "/original-fixture"}).json()
    conversation = first["metadata"]["conversation_db_id"]
    before = client.get(f"/v1/chat/conversations/{conversation}/messages").json()["items"]
    monkeypatch.setattr(
        engine,
        "route_chat_message",
        lambda text: ChatRouteDecision(
            route_type="conversation",
            routed_text=text,
            classification={},
        ),
    )

    def interrupted_reply(text, *, session, chat_id, **kwargs):
        assert engine.CONVERSATION_CACHE[chat_id] == []
        session.commit()  # An ingestion side effect can finish before the reply.
        raise RuntimeError("fictional interrupted provider")

    monkeypatch.setattr(engine, "generate_conversation_reply", interrupted_reply)
    failed = client.post(
        "/v1/chat", json={**base, "text": "Fictional replacement", "supersedes_message_id": first["user_message_id"]}
    )
    assert failed.status_code == 500
    after = client.get(f"/v1/chat/conversations/{conversation}/messages").json()["items"]
    assert after == before

    monkeypatch.setattr(engine, "generate_conversation_reply", lambda *a, **k: "A fictional answer")
    monkeypatch.setattr(engine, "build_memory_context_package", lambda *a, **k: "")
    retry = client.post(
        "/v1/chat", json={**base, "text": "Fictional replacement", "supersedes_message_id": first["user_message_id"]}
    )
    assert retry.status_code == 200
    visible = client.get(f"/v1/chat/conversations/{conversation}/messages").json()["items"]
    assert len(visible) == 2 and visible[0]["id"] == retry.json()["user_message_id"]
