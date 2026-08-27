"""The two numbers an alert would fire on must reach the scraper.

Queue depth and worker heartbeat age were both computed and both unreachable:
they existed only inside JSON from an authenticated endpoint, or were flattened
to an "ok"/"error" string by /ready. The Prometheus surface -- the one thing a
monitor reads -- carried no queue or worker signal at all.

A stalled worker is the failure that costs the most and shows the least: the API
stays green, every request succeeds, and entries simply never finish
processing.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

PASSPHRASE = "correct horse battery staple"


@pytest.fixture
def client(isolated_db):
    from thoughtpins.api import app

    return TestClient(app)


def _token(client: TestClient) -> str:
    email = "metrics-probe@thoughtpins.com"
    client.post("/v1/auth/register", json={"email": email, "password": PASSPHRASE})
    return client.post("/v1/auth/login", json={"identifier": email, "password": PASSPHRASE}).json()["access_token"]


def test_metrics_carry_queue_and_worker_gauges(client):
    response = client.get("/v1/metrics", headers={"Authorization": f"Bearer {_token(client)}"})
    assert response.status_code == 200, response.text
    body = response.text
    for gauge in (
        "thoughtpins_worker_heartbeat_age_seconds",
        "thoughtpins_queue_depth",
        "thoughtpins_worker_up",
    ):
        assert gauge in body, f"{gauge} missing from /v1/metrics"
        assert f"# TYPE {gauge} gauge" in body, f"{gauge} has no TYPE line, so a scraper will not read it"


def test_an_unreadable_worker_reports_minus_one_not_zero(client, monkeypatch):
    """-1 and 0 must not be confusable.

    A scraper cannot tell "zero jobs waiting" from "could not reach Redis", and
    alerting on the wrong one of those is worse than not alerting at all.
    """
    import thoughtpins.jobs as jobs

    monkeypatch.setattr(jobs, "worker_health", lambda: (_ for _ in ()).throw(RuntimeError("redis down")))
    response = client.get("/v1/metrics", headers={"Authorization": f"Bearer {_token(client)}"})
    assert response.status_code == 200
    assert "thoughtpins_queue_depth -1" in response.text
    assert "thoughtpins_worker_heartbeat_age_seconds -1" in response.text
    # `up` is the exception: unknown must read as down, or a monitor that
    # cannot reach the worker stays quiet.
    assert "thoughtpins_worker_up 0" in response.text
