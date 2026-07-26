"""Transport message IDs prevent duplicate asynchronous jobs."""

from fastapi.testclient import TestClient


def test_async_entry_message_id_enqueues_once(isolated_db, monkeypatch) -> None:
    import thoughtpins.api as api_module
    from thoughtpins.api import app
    from thoughtpins.config import config
    from thoughtpins.db import IngestionJob
    from thoughtpins.store import get_session

    monkeypatch.setattr(config, "PROCESS_ENTRIES_ASYNC", True)
    monkeypatch.setattr(type(config), "PROCESS_ENTRIES_ASYNC", True)
    enqueued: list[str] = []
    monkeypatch.setattr(api_module, "enqueue_ingestion_job", lambda job_id, user_id=None: enqueued.append(job_id))

    client = TestClient(app)
    payload = {"text": "A retry-safe asynchronous fixture.", "message_id": "mobile-message-0001"}
    first = client.post("/v1/entries", json=payload)
    second = client.post("/v1/entries", json=payload)

    assert first.status_code == second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]
    assert len(enqueued) == 1

    session = get_session()
    try:
        jobs = session.query(IngestionJob).all()
        assert len(jobs) == 1
        assert jobs[0].dedup_key == "api:mobile-message-0001"
        assert jobs[0].metadata_json["dedup_key"] == jobs[0].dedup_key
    finally:
        session.close()


def test_async_entry_queue_outage_is_retryable_with_same_message_id(isolated_db, monkeypatch) -> None:
    import thoughtpins.api as api_module
    from thoughtpins.api import app
    from thoughtpins.config import config
    from thoughtpins.db import IngestionJob
    from thoughtpins.store import get_session

    monkeypatch.setattr(config, "PROCESS_ENTRIES_ASYNC", True)
    monkeypatch.setattr(type(config), "PROCESS_ENTRIES_ASYNC", True)

    def queue_unavailable(job_id, user_id=None):
        raise ConnectionError("redis://private-host:6379")

    monkeypatch.setattr(api_module, "enqueue_ingestion_job", queue_unavailable)
    client = TestClient(app)
    payload = {"text": "A durable queue outage fixture.", "message_id": "mobile-message-outage"}

    first = client.post("/v1/entries", json=payload)
    assert first.status_code == 503
    assert "private-host" not in first.text

    session = get_session()
    try:
        stored = session.query(IngestionJob).one()
        assert stored.status == "retry"
        job_id = stored.id
    finally:
        session.close()

    published: list[str] = []
    monkeypatch.setattr(
        api_module, "enqueue_ingestion_job", lambda queued_id, user_id=None: published.append(queued_id)
    )
    retried = client.post("/v1/entries", json=payload)

    assert retried.status_code == 202
    assert retried.json()["job_id"] == job_id
    assert published == [job_id]
    session = get_session()
    try:
        assert session.query(IngestionJob).one().status == "queued"
    finally:
        session.close()
