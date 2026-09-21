"""HTTP idempotency behavior for mobile retries and offline outboxes."""

import pytest
from fastapi.testclient import TestClient


def _device_payload(name: str = "Primary browser") -> dict:
    return {
        "installation_id": "idempotency-web-install",
        "platform": "web",
        "device_name": name,
        "app_version": "0.2.0",
        "build_number": "test",
        "notifications_enabled": False,
    }


def test_mutation_replays_completed_response_without_duplicate_effect(isolated_db) -> None:
    from thoughtpins.api import app
    from thoughtpins.db import ApiIdempotencyRecord, AppDevice
    from thoughtpins.store import get_session

    client = TestClient(app)
    headers = {"Idempotency-Key": "device-create-0001"}
    first = client.post("/v1/devices", json=_device_payload(), headers=headers)
    second = client.post("/v1/devices", json=_device_payload(), headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    assert "X-Idempotent-Replay" not in first.headers
    assert second.headers["X-Idempotent-Replay"] == "true"

    session = get_session()
    try:
        assert session.query(AppDevice).count() == 1
        record = session.query(ApiIdempotencyRecord).one()
        assert record.status == "completed"
        assert record.response_status == 200
        assert record.request_hash
    finally:
        session.close()


def test_key_reuse_with_different_request_is_rejected(isolated_db) -> None:
    from thoughtpins.api import app

    client = TestClient(app)
    headers = {"Idempotency-Key": "device-create-0002"}
    assert client.post("/v1/devices", json=_device_payload(), headers=headers).status_code == 200

    conflict = client.post(
        "/v1/devices",
        json=_device_payload("Different browser"),
        headers=headers,
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"


def test_invalid_idempotency_key_uses_error_envelope(isolated_db) -> None:
    from thoughtpins.api import app

    response = TestClient(app).post(
        "/v1/devices",
        json=_device_payload(),
        headers={"Idempotency-Key": "bad key"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_idempotency_key"
    assert response.json()["error"]["request_id"]


@pytest.mark.parametrize("streamed", [False, True])
async def test_idempotency_accepts_both_response_contracts(monkeypatch, streamed):
    from starlette.requests import Request
    from starlette.responses import Response, StreamingResponse

    from thoughtpins import api_idempotency_http
    from thoughtpins.idempotency import IdempotencyClaim

    saved = []
    monkeypatch.setattr(api_idempotency_http, "_claim", lambda **kwargs: IdempotencyClaim("synthetic-record"))
    monkeypatch.setattr(api_idempotency_http, "_persist", lambda **kwargs: saved.append(kwargs))

    async def receive():
        return {"type": "http.request", "body": b"{}", "more_body": False}

    expected = b'{"saved":true}'

    async def next_response(request):
        if streamed:
            return StreamingResponse(iter([expected[:4], expected[4:]]), media_type="application/json")
        return Response(expected, media_type="application/json")

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/synthetic",
            "query_string": b"",
            "headers": [(b"idempotency-key", b"synthetic-retry-001")],
        },
        receive,
    )
    response = await api_idempotency_http.call_with_idempotency(request, next_response, user_id="synthetic-owner")
    assert response.status_code == 200
    assert response.body == expected
    assert len(saved) == 1
    assert saved[0]["response_body"] == expected
    assert saved[0]["user_id"] == "synthetic-owner"
    assert saved[0]["replayable"] is True
