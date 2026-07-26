"""End-to-end smoke test for a running Thought Pins API.

This script is intentionally black-box: it talks to HTTP only and can run
against local Docker Compose, staging, or production with a dedicated test user.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.getenv(key, "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


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


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the disposable HTTP API smoke workflow.")
    parser.add_argument(
        "--base-url",
        default=os.getenv("THOUGHTPINS_BASE_URL", "http://127.0.0.1:8420"),
        help="API origin. Defaults to THOUGHTPINS_BASE_URL or the local API.",
    )
    parser.add_argument(
        "--register",
        action=argparse.BooleanOptionalAction,
        default=_env_bool("THOUGHTPINS_SMOKE_REGISTER", True),
        help="Create a disposable account for the workflow.",
    )
    parser.add_argument(
        "--delete-account",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Delete a newly created smoke account before exit (default: same as --register).",
    )
    parser.add_argument(
        "--wait-job",
        action=argparse.BooleanOptionalAction,
        default=_env_bool("THOUGHTPINS_SMOKE_WAIT_JOB", False),
        help="Wait for asynchronous ingestion completion.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    base_url = args.base_url.rstrip("/")
    register_user = bool(args.register)
    delete_account = (
        _env_bool("THOUGHTPINS_SMOKE_DELETE_ACCOUNT", register_user)
        if args.delete_account is None
        else bool(args.delete_account)
    )
    wait_for_job = bool(args.wait_job)
    email = os.getenv("THOUGHTPINS_SMOKE_EMAIL", f"smoke+{uuid4().hex[:10]}@example.com")
    password = os.getenv("THOUGHTPINS_SMOKE_PASSWORD", "correct horse battery staple")
    http_timeout = float(os.getenv("THOUGHTPINS_SMOKE_HTTP_TIMEOUT_SECONDS", "60"))
    entry_text = os.getenv(
        "THOUGHTPINS_SMOKE_ENTRY",
        f"Smoke test entry {uuid4().hex[:8]}: checked backend health, auth, entry queue, and export.",
    )

    print(f"smoke base_url={base_url}")
    with httpx.Client(base_url=base_url, timeout=http_timeout) as client:
        health = _expect(client.get("/health"), 200)
        print("health:", _json(health).get("status"))

        errors = _expect(client.get("/v1/errors"), 200)
        assert "validation_error" in _json(errors).get("codes", {})
        print("errors: ok")

        created_user = False
        if register_user:
            register = client.post(
                "/v1/auth/register",
                json={"email": email, "password": password},
            )
            if register.status_code == 200:
                created_user = True
                print("register: ok")
            elif register.status_code == 403 and _can_seed_local_smoke_user(base_url):
                _seed_local_smoke_user(email, password)
                created_user = True
                print("register: seeded disposable local smoke user")
            elif register.status_code in {403, 409}:
                print(f"register: skipped ({register.status_code}); using login credentials")
            else:
                _expect(register, 200)

        login = _expect(client.post("/v1/auth/login", json={"email": email, "password": password}), 200)
        token = _json(login)["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("login: ok")

        me = _expect(client.get("/v1/me", headers=headers), 200)
        user_id = _json(me).get("id")
        print(f"me: {user_id}")

        deep = _expect(client.get("/v1/health/deep", headers=headers), 200)
        print("deep health:", _json(deep).get("status"))

        ingest = _expect(client.post("/v1/entries", headers=headers, json={"text": entry_text}), 200, 202)
        ingest_body = _json(ingest)
        print("entry:", ingest.status_code, ingest_body.get("status"))

        job_id = ingest_body.get("job_id")
        if job_id:
            job = _expect(client.get(f"/v1/jobs/{job_id}", headers=headers), 200)
            print("job:", _json(job).get("status"))
            jobs = _expect(client.get("/v1/jobs?page=1&limit=5", headers=headers), 200)
            assert _json(jobs).get("total", 0) >= 1
            if wait_for_job:
                _wait_for_job(client, headers, job_id)

        entries = _expect(client.get("/v1/entries?page=1&limit=5", headers=headers), 200)
        print("entries:", _json(entries).get("total"))

        export = _expect(client.get("/v1/export", headers=headers), 200)
        assert "tables" in _json(export)
        print("export: ok")

        if delete_account and created_user:
            deleted = _expect(client.request("DELETE", "/v1/me", headers=headers, json={"confirm": "DELETE"}), 200)
            print("delete:", _json(deleted).get("status"))
        elif delete_account:
            print("delete: skipped because this was not a newly-created smoke user")

    print("smoke passed")
    return 0


def _can_seed_local_smoke_user(base_url: str) -> bool:
    if not _env_bool("THOUGHTPINS_SMOKE_SEED_LOCAL", True):
        return False
    host = (urlparse(base_url).hostname or "").lower()
    return host in {"127.0.0.1", "localhost", "::1"}


def _seed_local_smoke_user(email: str, password: str) -> None:
    from thoughtpins.auth import hash_password
    from thoughtpins.store import get_session
    from thoughtpins.users import get_user_by_email, register_user

    session = get_session()
    try:
        existing = get_user_by_email(email, session=session)
        if existing:
            existing.password_hash = hash_password(password)
            existing.is_active = True
            existing.deleted_at_utc = None
            prefs = dict(existing.preferences_json or {})
            prefs.setdefault("email_verification", {"verified": True, "source": "local_smoke"})
            existing.preferences_json = prefs
            session.commit()
            return
        register_user(
            email=email,
            display_name="Local Smoke User",
            password_hash=hash_password(password),
            session=session,
            bypass_system_lock=True,
        )
    finally:
        session.close()


def _wait_for_job(client: httpx.Client, headers: dict[str, str], job_id: str) -> None:
    deadline = time.time() + int(os.getenv("THOUGHTPINS_SMOKE_JOB_TIMEOUT_SECONDS", "120"))
    terminal = {"completed", "failed", "dead_letter", "canceled"}
    while time.time() < deadline:
        job = _expect(client.get(f"/v1/jobs/{job_id}", headers=headers), 200)
        status = _json(job).get("status")
        if status in terminal:
            if status != "completed":
                raise RuntimeError(f"Job ended as {status}: {_json(job).get('error')}")
            print("job completed")
            return
        time.sleep(2)
    raise TimeoutError(f"Timed out waiting for job {job_id}")


if __name__ == "__main__":
    sys.exit(main())
