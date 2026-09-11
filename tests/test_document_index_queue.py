from __future__ import annotations

import asyncio


def test_document_index_queue_flushes_deferred_payload(monkeypatch):
    from thoughtpins import library
    from thoughtpins.db import Memory

    seen: list[list[tuple[str, str, str]]] = []

    memory = Memory(
        id="memory_deferred_index",
        text="Deferred vector indexing should drain before shutdown.",
        user_id="tenant-deferred-index",
    )

    monkeypatch.setattr(library, "_index_document_memory_payloads", lambda payload: seen.append(payload))

    library.schedule_document_memory_indexing([memory])

    assert library.flush_document_indexing(timeout_seconds=2.0) is True
    assert seen == [
        [
            (
                "memory_deferred_index",
                "Deferred vector indexing should drain before shutdown.",
                "tenant-deferred-index",
            )
        ]
    ]
    assert library.document_indexing_backlog() == 0


def test_api_lifespan_drains_document_index_queue_on_shutdown(monkeypatch):
    from thoughtpins import api

    calls: list[int] = []
    config_cls = type(api.config)
    old_values = {
        "RUN_STARTUP_RECOVERY": (api.config.RUN_STARTUP_RECOVERY, config_cls.RUN_STARTUP_RECOVERY),
        "PROCESS_ENTRIES_ASYNC": (api.config.PROCESS_ENTRIES_ASYNC, config_cls.PROCESS_ENTRIES_ASYNC),
        "DOCUMENT_INDEX_DRAIN_TIMEOUT_SECONDS": (
            api.config.DOCUMENT_INDEX_DRAIN_TIMEOUT_SECONDS,
            config_cls.DOCUMENT_INDEX_DRAIN_TIMEOUT_SECONDS,
        ),
    }

    monkeypatch.setattr(api, "init_db", lambda: None)
    monkeypatch.setattr(api, "_recover_orphaned_entries", lambda: None)
    monkeypatch.setattr(api, "recover_pending_jobs", lambda: None)

    def flush(timeout_seconds: int) -> bool:
        calls.append(timeout_seconds)
        return True

    monkeypatch.setattr(api, "flush_document_indexing", flush)
    monkeypatch.setattr(api.config, "RUN_STARTUP_RECOVERY", False)
    monkeypatch.setattr(config_cls, "RUN_STARTUP_RECOVERY", False)
    monkeypatch.setattr(api.config, "PROCESS_ENTRIES_ASYNC", False)
    monkeypatch.setattr(config_cls, "PROCESS_ENTRIES_ASYNC", False)
    monkeypatch.setattr(api.config, "DOCUMENT_INDEX_DRAIN_TIMEOUT_SECONDS", 7)
    monkeypatch.setattr(config_cls, "DOCUMENT_INDEX_DRAIN_TIMEOUT_SECONDS", 7)

    async def run_lifespan() -> None:
        async with api.lifespan(api.app):
            pass

    try:
        asyncio.run(run_lifespan())
    finally:
        for key, (instance_value, class_value) in old_values.items():
            setattr(api.config, key, instance_value)
            setattr(config_cls, key, class_value)

    assert calls == [7]


def test_vector_health_reports_deferred_document_index_backlog(monkeypatch):
    from thoughtpins import runtime_health
    from thoughtpins.config import config

    config_cls = type(config)
    old_values = {
        "EMBEDDING_PROVIDER": (config.EMBEDDING_PROVIDER, config_cls.EMBEDDING_PROVIDER),
        "VECTOR_HEALTHCHECK_LIVE": (config.VECTOR_HEALTHCHECK_LIVE, config_cls.VECTOR_HEALTHCHECK_LIVE),
    }
    monkeypatch.setattr(config, "EMBEDDING_PROVIDER", "local")
    monkeypatch.setattr(config_cls, "EMBEDDING_PROVIDER", "local")
    monkeypatch.setattr(config, "VECTOR_HEALTHCHECK_LIVE", False)
    monkeypatch.setattr(config_cls, "VECTOR_HEALTHCHECK_LIVE", False)
    monkeypatch.setattr("thoughtpins.library.document_indexing_backlog", lambda: 3)

    try:
        health = runtime_health.vector_health()
    finally:
        for key, (instance_value, class_value) in old_values.items():
            setattr(config, key, instance_value)
            setattr(config_cls, key, class_value)

    assert health["status"] == "configured"
    assert health["document_index_backlog"] == 3
