"""Black-box runtime smoke for the main Thought Pins product loop."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from smoke_api import _can_seed_local_smoke_user, _env_bool, _expect, _json, _seed_local_smoke_user  # noqa: E402


def main() -> int:
    base_url = os.getenv("THOUGHTPINS_BASE_URL", "http://127.0.0.1:8420").rstrip("/")
    marker = f"runtime-{uuid4().hex[:8]}"
    email = os.getenv("THOUGHTPINS_RUNTIME_SMOKE_EMAIL", f"runtime+{uuid4().hex[:10]}@example.com")
    password = os.getenv("THOUGHTPINS_RUNTIME_SMOKE_PASSWORD", "correct horse battery staple")
    delete_account = _env_bool("THOUGHTPINS_RUNTIME_SMOKE_DELETE_ACCOUNT", True)
    http_timeout = float(os.getenv("THOUGHTPINS_RUNTIME_SMOKE_HTTP_TIMEOUT_SECONDS", "60"))

    print(f"runtime smoke base_url={base_url}")
    with httpx.Client(base_url=base_url, timeout=http_timeout) as client:
        created_user = _register_or_seed(client, base_url, email, password)
        login = _expect(client.post("/v1/auth/login", json={"email": email, "password": password}), 200)
        token = _json(login)["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("login: ok")

        deep = _expect(client.get("/v1/health/deep", headers=headers), 200)
        assert _json(deep).get("status") == "ok"
        print("deep health: ok")

        chat = _expect(
            client.post(
                "/v1/chat",
                headers=headers,
                json={"text": "hey thought pins, quick runtime check", "conversation_id": marker},
            ),
            200,
        )
        assert _json(chat).get("route_type") == "chat"
        print("casual chat: ok")

        journal_text = f"journal: {marker}: met Mira at Atlas Cafe and decided the copper lantern detail matters for runtime recall."
        journal = _expect(
            client.post("/v1/chat", headers=headers, json={"text": journal_text, "conversation_id": marker}), 200
        )
        journal_body = _json(journal)
        assert journal_body.get("route_type") == "journal_entry"
        _wait_for_optional_job(client, headers, journal_body.get("job_id"))
        print("journal save: ok")

        article_text = (
            f"Runtime article marker {marker}. The article says the copper lantern detail should be filed "
            "as source memory with exact provenance. It mentions Atlas Cafe and Mira as retrieval anchors."
        )
        library = _expect(
            client.post(
                "/v1/library",
                headers=headers,
                json={"text": article_text, "title": f"Runtime Source {marker}", "source_type": "article"},
            ),
            200,
        )
        assert _json(library).get("document_id")
        print("article save: ok")

        recall = _expect(
            client.post("/v1/chat", headers=headers, json={"text": f"search {marker}", "conversation_id": marker}), 200
        )
        recall_text = (_json(recall).get("reply") or "").lower()
        assert marker.lower() in recall_text or "copper lantern" in recall_text
        print("memory recall: ok")

        correction = _expect(
            client.post(
                "/v1/chat",
                headers=headers,
                json={"text": "Actually Mira is spelled Meera for that runtime note", "conversation_id": marker},
            ),
            200,
        )
        assert _json(correction).get("route_type") == "correction"
        print("correction: ok")

        undo = _expect(
            client.post("/v1/chat", headers=headers, json={"text": "undo that", "conversation_id": marker}), 200
        )
        undo_body = _json(undo)
        assert undo_body.get("requires_confirmation") is True
        pending_id = (undo_body.get("metadata") or {}).get("pending_action_id")
        confirm = _expect(
            client.post(
                "/v1/chat",
                headers=headers,
                json={
                    "text": "confirm undo",
                    "conversation_id": marker,
                    "pending_action_id": pending_id,
                    "confirm_action": True,
                },
            ),
            200,
        )
        assert _json(confirm).get("status") == "undone"
        print("undo confirmation: ok")

        export = _expect(client.post("/v1/export/vault?zip=true&obsidian_defaults=true", headers=headers), 200)
        export_body = _json(export)
        assert export_body.get("format") == "obsidian_compatible_vault"
        assert export_body.get("stats", {}).get("validation_errors") == 0
        print("vault export: ok")

        if delete_account and created_user:
            deleted = _expect(client.request("DELETE", "/v1/me", headers=headers, json={"confirm": "DELETE"}), 200)
            assert _json(deleted).get("status") == "deleted"
            print("account deletion: ok")
        elif delete_account:
            print("account deletion: skipped because this was not a disposable smoke user")

    print("runtime feature smoke passed")
    return 0


def _register_or_seed(client: httpx.Client, base_url: str, email: str, password: str) -> bool:
    register = client.post("/v1/auth/register", json={"email": email, "password": password})
    if register.status_code == 200:
        print("register: ok")
        return True
    if register.status_code == 403 and _can_seed_local_smoke_user(base_url):
        _seed_local_smoke_user(email, password)
        print("register: seeded disposable local smoke user")
        return True
    if register.status_code == 409:
        print("register: existing smoke user")
        return False
    _expect(register, 200)
    return True


def _wait_for_optional_job(client: httpx.Client, headers: dict[str, str], job_id: str | None) -> None:
    if not job_id:
        return
    deadline = time.time() + 120
    while time.time() < deadline:
        job = _expect(client.get(f"/v1/jobs/{job_id}", headers=headers), 200)
        status = _json(job).get("status")
        if status in {"completed", "failed", "dead_letter", "canceled"}:
            assert status == "completed"
            return
        time.sleep(2)
    raise TimeoutError(f"Timed out waiting for job {job_id}")


if __name__ == "__main__":
    raise SystemExit(main())
