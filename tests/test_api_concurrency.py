"""A held synchronous dependency must not freeze unrelated ASGI requests."""

from __future__ import annotations

import ast
import asyncio
import threading
from pathlib import Path

import httpx
import pytest


@pytest.mark.parametrize("boundary", ["identity", "rate_limit", "idempotency_hash", "idempotency", "database_route"])
async def test_blocking_request_keeps_health_responsive(isolated_db, monkeypatch, boundary):
    from thoughtpins import api, api_idempotency_http
    from thoughtpins.api_routes import account
    from thoughtpins.tenancy import get_current_tenant_id

    entered, release = threading.Event(), threading.Event()
    loop_thread = threading.get_ident()
    observed = []
    target, name = {
        "identity": (api, "_resolve_request_user"),
        "rate_limit": (api, "check_rate_limit"),
        "idempotency_hash": (api_idempotency_http, "request_hash"),
        "idempotency": (api_idempotency_http, "claim_request"),
        "database_route": (account, "get_session"),
    }[boundary]
    original = getattr(target, name)

    def held(*args, **kwargs):
        observed.append((threading.get_ident(), get_current_tenant_id()))
        entered.set()
        if not release.wait(3):
            raise TimeoutError("Test dependency was not released while health was served")
        return original(*args, **kwargs)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="http://test") as client:
        identity = (await client.get("/v1/me")).json()
        monkeypatch.setattr(target, name, held)
        if boundary in {"idempotency_hash", "idempotency"}:
            task = asyncio.create_task(
                client.post(
                    "/v1/devices",
                    headers={"Idempotency-Key": "concurrency-fixture-001"},
                    json={"installation_id": "concurrency-fixture", "platform": "web"},
                )
            )
        else:
            task = asyncio.create_task(client.get("/v1/me"))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            assert observed[0][0] != loop_thread
            if boundary in {"idempotency_hash", "idempotency", "database_route"}:
                assert observed[0][1] == identity["id"]
            health = await asyncio.wait_for(client.get("/health"), timeout=1)
            assert health.status_code == 200
            assert not task.done(), "The slow request should still be held"
        finally:
            release.set()
            response = await asyncio.wait_for(task, timeout=5)
        assert response.status_code == 200


def test_only_nonblocking_metadata_routes_run_on_event_loop():
    # Normal def lets FastAPI offload the entire transaction, including session
    # construction and response projection, instead of sharing a Session across threads.
    asynchronous = {
        node.name
        for path in (Path(__file__).parents[1] / "src/thoughtpins/api_routes").glob("*.py")
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.AsyncFunctionDef) and node.decorator_list
    }
    assert asynchronous == {"health", "readiness", "error_catalog", "client_config"}
