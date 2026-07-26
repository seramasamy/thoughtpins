"""Local founder smoke test for a locked no-auth development runtime.

This validates the product surface used during founder Telegram/web testing
without requiring public registration to be open. It talks to the running API,
then removes the disposable durable chat transcript directly from the local DB.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _expect(response: httpx.Response, *statuses: int) -> httpx.Response:
    if response.status_code not in statuses:
        print(f"{response.request.method} {response.request.url} -> {response.status_code}")
        print(response.text[:1000])
        response.raise_for_status()
    return response


def _json(response: httpx.Response) -> dict:
    try:
        return response.json()
    except Exception:
        return {}


def main() -> int:
    base_url = os.getenv("THOUGHTPINS_BASE_URL", "http://127.0.0.1:8420").rstrip("/")
    conversation_id = f"founder-smoke-{uuid4().hex[:10]}"
    conversation_key = f"web:{conversation_id}"

    print(f"founder smoke base_url={base_url}")
    with httpx.Client(base_url=base_url, timeout=30) as client:
        health = _expect(client.get("/v1/health"), 200)
        assert _json(health).get("status") == "ok"
        print("health: ok")

        deep = _expect(client.get("/v1/health/deep"), 200)
        deep_body = _json(deep)
        assert deep_body.get("status") == "ok"
        checks = deep_body.get("checks") or {}
        llm = checks.get("llm") or {}
        vector = checks.get("vector") or {}
        assert llm.get("configured") is True
        assert "model" not in llm
        assert "provider" not in llm
        assert vector.get("status") in {"ok", "configured"}
        assert "embedding_model" not in vector
        print("deep health: ok")

        chat = _expect(
            client.post(
                "/v1/chat",
                json={
                    "text": "status",
                    "surface": "web",
                    "conversation_id": conversation_id,
                },
            ),
            200,
        )
        chat_body = _json(chat)
        assert chat_body.get("status") == "replied"
        conversation_db_id = (chat_body.get("metadata") or {}).get("conversation_db_id")
        assert conversation_db_id
        print("chat: ok")

        conversations = _expect(client.get("/v1/chat/conversations?surface=web&limit=20"), 200)
        assert any(item.get("id") == conversation_db_id for item in _json(conversations).get("items", []))
        print("conversations: ok")

        messages = _expect(client.get(f"/v1/chat/conversations/{conversation_db_id}/messages?limit=10"), 200)
        roles = [item.get("role") for item in _json(messages).get("items", [])]
        assert roles == ["user", "assistant"]
        print("messages: ok")

    _cleanup_conversation(conversation_key)
    print("cleanup: ok")
    print("founder smoke passed")
    return 0


def _cleanup_conversation(conversation_key: str) -> None:
    from thoughtpins.db import ChatConversation
    from thoughtpins.store import get_session

    session = get_session()
    try:
        conversation = (
            session.query(ChatConversation).filter(ChatConversation.conversation_key == conversation_key).first()
        )
        if conversation:
            session.delete(conversation)
            session.commit()
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
