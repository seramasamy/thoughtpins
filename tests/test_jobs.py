from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_run_ingestion_job_marks_completed(isolated_db, monkeypatch):
    from thoughtpins.db import IngestionJob, RawEntry
    from thoughtpins.jobs import create_ingestion_job, run_ingestion_job
    from thoughtpins.store import get_session
    from thoughtpins.users import register_user
    from thoughtpins.utils import hash_text

    user = register_user(email="job@example.com")
    session = get_session()
    try:
        job = create_ingestion_job(session, user_id=user.id, text="Remember this.", source="api")
        job_id = job.id
    finally:
        session.close()

    def fake_process_message(session, text, **kwargs):
        assert text == "Remember this."
        assert kwargs["user_id"] == user.id
        entry = RawEntry(
            user_id=user.id,
            raw_text=text,
            content_hash=hash_text(text),
            processed_status="completed",
        )
        session.add(entry)
        session.flush()
        return {"type": "journal_stored", "entry_id": entry.id}

    monkeypatch.setattr("thoughtpins.jobs.process_message", fake_process_message)
    run_ingestion_job(job_id)

    session = get_session()
    try:
        stored = session.query(IngestionJob).filter_by(id=job_id).first()
        assert stored.status == "completed"
        assert stored.entry_id is not None
        assert stored.finished_at_utc is not None
    finally:
        session.close()


def test_get_or_create_job_is_tenant_scoped_and_stable(isolated_db):
    from thoughtpins.jobs import get_or_create_ingestion_job
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user

    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        first, created_first = get_or_create_ingestion_job(
            session,
            user_id=user.id,
            text="One logical entry",
            dedup_key="api:message-0001",
        )
        second, created_second = get_or_create_ingestion_job(
            session,
            user_id=user.id,
            text="One logical entry",
            dedup_key="api:message-0001",
        )
        assert created_first is True
        assert created_second is False
        assert first.id == second.id
    finally:
        session.close()


def test_dispatch_is_single_publish_and_moves_job_to_queued(isolated_db):
    from thoughtpins.db import IngestionJob
    from thoughtpins.jobs import create_ingestion_job, dispatch_ingestion_job
    from thoughtpins.store import get_session
    from thoughtpins.users import register_user

    user = register_user(email="dispatch-once@example.com")
    session = get_session()
    published: list[tuple[str, str | None]] = []
    try:
        job = create_ingestion_job(session, user_id=user.id, text="Publish once.")
        assert dispatch_ingestion_job(
            session,
            job,
            user_id=user.id,
            enqueue_fn=lambda job_id, user_id=None: published.append((job_id, user_id)),
        )
        session.refresh(job)
        assert job.status == "queued"
        assert job.queued_at_utc is not None
        assert not dispatch_ingestion_job(
            session,
            job,
            user_id=user.id,
            enqueue_fn=lambda job_id, user_id=None: published.append((job_id, user_id)),
        )
        assert published == [(job.id, user.id)]
        assert session.query(IngestionJob).filter_by(id=job.id).one().status == "queued"
    finally:
        session.close()


def test_dispatch_failure_preserves_retryable_job(isolated_db):
    import pytest

    from thoughtpins.db import IngestionJob
    from thoughtpins.jobs import IngestionDispatchUnavailable, create_ingestion_job, dispatch_ingestion_job
    from thoughtpins.store import get_session
    from thoughtpins.users import register_user

    user = register_user(email="dispatch-failure@example.com")
    session = get_session()
    try:
        job = create_ingestion_job(session, user_id=user.id, text="Keep this durable.")

        def unavailable(*args, **kwargs):
            raise ConnectionError("broker detail must stay internal")

        with pytest.raises(IngestionDispatchUnavailable):
            dispatch_ingestion_job(session, job, user_id=user.id, enqueue_fn=unavailable)

        stored = session.query(IngestionJob).filter_by(id=job.id).one()
        assert stored.status == "retry"
        assert stored.error == "The processing queue is temporarily unavailable."
        assert "broker detail" not in stored.error
    finally:
        session.close()


def test_recover_pending_jobs_requeues_stale_running_jobs(isolated_db, monkeypatch):
    from thoughtpins.db import IngestionJob
    from thoughtpins.jobs import create_ingestion_job, recover_pending_jobs
    from thoughtpins.store import get_session
    from thoughtpins.users import register_user

    queued: list[str] = []
    monkeypatch.setattr("thoughtpins.jobs.enqueue_ingestion_job", lambda job_id, user_id=None: queued.append(job_id))

    user = register_user(email="recover@example.com")
    session = get_session()
    try:
        job = create_ingestion_job(session, user_id=user.id, text="Recover this.", source="api")
        job.status = "running"
        job.started_at_utc = _utcnow() - timedelta(hours=2)
        session.commit()
        job_id = job.id
    finally:
        session.close()

    assert recover_pending_jobs() == 1
    assert queued == [job_id]

    session = get_session()
    try:
        stored = session.query(IngestionJob).filter_by(id=job_id).first()
        assert stored.status == "queued"
        assert stored.error is None
        assert stored.metadata_json["last_recovery_reason"] == "stale_worker_claim"
    finally:
        session.close()


def test_failed_job_moves_to_dead_letter_after_retries(isolated_db, monkeypatch):
    from thoughtpins.config import config
    from thoughtpins.db import IngestionJob
    from thoughtpins.jobs import create_ingestion_job, run_ingestion_job
    from thoughtpins.store import get_session
    from thoughtpins.users import register_user

    monkeypatch.setattr(config, "INGESTION_MAX_RETRIES", 1)
    monkeypatch.setattr(type(config), "INGESTION_MAX_RETRIES", 1)
    monkeypatch.setattr("thoughtpins.jobs.enqueue_ingestion_job", lambda job_id: None)

    user = register_user(email="deadletter@example.com")
    session = get_session()
    try:
        job = create_ingestion_job(session, user_id=user.id, text="Break this.", source="api")
        job_id = job.id
    finally:
        session.close()

    def fail_process_message(session, text, **kwargs):
        raise RuntimeError("llm unavailable")

    monkeypatch.setattr("thoughtpins.jobs.process_message", fail_process_message)
    run_ingestion_job(job_id)
    run_ingestion_job(job_id)

    session = get_session()
    try:
        stored = session.query(IngestionJob).filter_by(id=job_id).first()
        assert stored.status == "dead_letter"
        assert stored.metadata_json["dead_letter_reason"] == "llm unavailable"
    finally:
        session.close()


def test_duplicate_worker_deliveries_claim_job_once(isolated_db, monkeypatch):
    from thoughtpins.jobs import create_ingestion_job, dispatch_ingestion_job, run_ingestion_job
    from thoughtpins.store import get_session
    from thoughtpins.users import register_user

    user = register_user(email="worker-claim@example.com")
    session = get_session()
    try:
        job = create_ingestion_job(session, user_id=user.id, text="Exactly once extraction.")
        dispatch_ingestion_job(session, job, user_id=user.id, enqueue_fn=lambda *args, **kwargs: None)
        job_id = job.id
    finally:
        session.close()

    entered = threading.Event()
    release = threading.Event()
    calls = 0
    calls_lock = threading.Lock()

    def fake_process_message(session, text, **kwargs):
        nonlocal calls
        with calls_lock:
            calls += 1
        entered.set()
        assert release.wait(timeout=5)
        return {"type": "journal_stored", "entry_id": None}

    monkeypatch.setattr("thoughtpins.jobs.process_message", fake_process_message)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(run_ingestion_job, job_id, user.id)
        assert entered.wait(timeout=5)
        second = executor.submit(run_ingestion_job, job_id, user.id)
        second.result(timeout=5)
        release.set()
        first.result(timeout=5)

    assert calls == 1
