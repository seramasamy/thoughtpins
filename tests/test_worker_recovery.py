from __future__ import annotations


def test_worker_recovery_relay_is_throttled(monkeypatch) -> None:
    import thoughtpins.worker as worker
    from thoughtpins.config import config

    clock = [100.0]
    calls: list[float] = []
    monkeypatch.setattr(config, "WORKER_RECOVERY_INTERVAL_SECONDS", 60)
    monkeypatch.setattr(type(config), "WORKER_RECOVERY_INTERVAL_SECONDS", 60)
    monkeypatch.setattr(worker.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(worker, "recover_pending_jobs", lambda: calls.append(clock[0]) or 2)
    monkeypatch.setattr(worker, "recover_vault_import_sessions", lambda: 0)
    monkeypatch.setattr(worker, "_last_recovery_monotonic", 0.0)

    assert worker.recover_jobs_if_due() == 2
    assert worker.recover_jobs_if_due() == 0
    clock[0] += 61
    assert worker.recover_jobs_if_due() == 2
    assert calls == [100.0, 161.0]


def test_worker_recovery_failure_does_not_break_heartbeat_loop(monkeypatch) -> None:
    import thoughtpins.worker as worker

    monkeypatch.setattr(worker, "_last_recovery_monotonic", 0.0)
    monkeypatch.setattr(worker, "recover_pending_jobs", lambda: (_ for _ in ()).throw(RuntimeError("db down")))
    monkeypatch.setattr(worker, "recover_vault_import_sessions", lambda: 0)

    assert worker.recover_jobs_if_due(force=True) == 0


def test_worker_recovery_queues_are_failure_isolated(monkeypatch) -> None:
    import thoughtpins.worker as worker

    monkeypatch.setattr(worker, "_last_recovery_monotonic", 0.0)
    monkeypatch.setattr(worker, "recover_pending_jobs", lambda: (_ for _ in ()).throw(RuntimeError("jobs down")))
    monkeypatch.setattr(worker, "recover_vault_import_sessions", lambda: 3)

    assert worker.recover_jobs_if_due(force=True) == 3
