"""TD-008: an entry saved through the app writes its memories to the vector index.

The first test is the assertion that would have caught the gap: save through
the API, then count vectors. The rest pin the contract around it. An embedding
failure never fails a save, and the repair sweep indexes what was missed.
Deletion wins every race with indexing, because a vector's payload holds the
memory's text.
"""

from __future__ import annotations

import zlib

import pytest
from fastapi.testclient import TestClient

PASSPHRASE = "correct horse battery staple"
ENTRY = "Walked the Harbour Market with Priya and planned the Northstar launch."
SENTINEL = "QVXL3-MARMOSET-CAPSTAN-SENTINEL-4b1d"
DIMENSION = 256


def _vector(text: str) -> list[float]:
    """Bag of words: texts that share words land near each other."""
    vector = [0.0] * DIMENSION
    for word in text.lower().replace(".", " ").split():
        vector[zlib.crc32(word.encode()) % DIMENSION] += 1.0
    return vector


@pytest.fixture
def embedder(isolated_db, monkeypatch):
    """Indexing on, with a deterministic embedder that a test can make fail."""
    from thoughtpins.config import config
    from thoughtpins.llm import ExtractedMemory, ExtractionResult
    from thoughtpins.memory.vector_store import close_vector_store

    for target in (config, type(config)):
        monkeypatch.setattr(target, "VECTOR_INDEX_ON_INGEST", True)
        # The "llm" provider embeds through get_embeddings, which is stubbed here.
        monkeypatch.setattr(target, "EMBEDDING_PROVIDER", "llm")
    state: dict = {"fail": False, "calls": 0, "before_return": None}

    def embed(texts: list[str]) -> list[list[float]]:
        state["calls"] += 1
        if state["fail"]:
            # A provider error that quotes its input must still stay out of the logs.
            raise ConnectionError(f"embedding provider unreachable while sending {texts[0]!r}")
        callback, state["before_return"] = state["before_return"], None
        if callback is not None:
            callback()
        return [_vector(text) for text in texts]

    monkeypatch.setattr("thoughtpins.llm.client.get_embeddings", embed)
    monkeypatch.setattr(
        "thoughtpins.ingestion.pipeline.classify_message",
        lambda text: {"type": "journal_entry", "intent": "test"},
    )
    monkeypatch.setattr(
        "thoughtpins.ingestion.pipeline.extract_from_entry",
        lambda text, local_datetime: ExtractionResult(memories=[ExtractedMemory(memory_type="event", text=text)]),
    )
    close_vector_store()
    yield state
    close_vector_store()


@pytest.fixture
def client(embedder):
    from thoughtpins.api import app

    return TestClient(app)


@pytest.fixture
def loguru_lines():
    from loguru import logger

    lines: list[str] = []
    sink = logger.add(lambda message: lines.append(str(message)), level="DEBUG", backtrace=False, diagnose=False)
    yield lines
    logger.remove(sink)


def _sign_in(client: TestClient, email: str) -> tuple[str, dict[str, str]]:
    assert client.post("/v1/auth/register", json={"email": email, "password": PASSPHRASE}).status_code == 200
    tokens = client.post("/v1/auth/login", json={"identifier": email, "password": PASSPHRASE}).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    client.post("/v1/legal/acceptances", headers=headers, json={"document": "ai_disclosure", "version": "2026-07-13"})
    me = client.get("/v1/me", headers=headers).json()
    return me.get("user_id") or me["id"], headers


def _save(client: TestClient, headers: dict[str, str], text: str = ENTRY) -> str:
    response = client.post("/v1/entries", headers=headers, json={"text": text})
    assert response.status_code == 200, response.text
    return response.json()["entry_id"]


def _save_unindexed(client: TestClient, headers: dict[str, str], embedder: dict) -> str:
    """Save while the provider is down, leaving an entry for a test to index."""
    embedder["fail"] = True
    try:
        return _save(client, headers)
    finally:
        embedder["fail"] = False


def _memory_ids(entry_id: str) -> list[str]:
    from thoughtpins.db import Memory
    from thoughtpins.store import get_session

    with get_session() as session:
        return [row[0] for row in session.query(Memory.id).filter(Memory.raw_entry_id == entry_id).all()]


def _store():
    from thoughtpins.memory.vector_store import get_vector_store

    return get_vector_store()


def test_saving_an_entry_through_the_api_writes_its_vectors(client):
    user_id, headers = _sign_in(client, "vectors-on-save@thoughtpins.com")
    before = _store().count()

    entry_id = _save(client, headers)

    memory_ids = _memory_ids(entry_id)
    assert memory_ids, "the stubbed extraction should have produced a memory"
    assert _store().count() == before + len(memory_ids)
    assert _store().missing_ids(memory_ids) == []
    hits = _store().search("planned the Northstar launch", limit=3, user_id=user_id)
    assert hits and hits[0]["id"] in memory_ids
    assert _store().search("planned the Northstar launch", limit=3, user_id="someone-else") == []


def test_a_failed_embedding_keeps_the_save_and_the_repair_sweep_indexes_it(client, embedder, loguru_lines):
    from thoughtpins.db import RawEntry
    from thoughtpins.memory.entry_vectors import repair_entry_vectors
    from thoughtpins.store import get_session

    _, headers = _sign_in(client, "vectors-retry@thoughtpins.com")
    embedder["fail"] = True

    entry_id = _save(client, headers, f"{ENTRY} {SENTINEL}")

    with get_session() as session:
        assert session.get(RawEntry, entry_id).processed_status == "completed"
    memory_ids = _memory_ids(entry_id)
    assert memory_ids and _store().missing_ids(memory_ids) == memory_ids, "nothing may be stored as if indexed"
    rendered = "\n".join(loguru_lines)
    assert "the repair sweep will retry" in rendered and "ConnectionError" in rendered
    assert SENTINEL not in rendered

    embedder["fail"] = False
    repaired = repair_entry_vectors(lookback_hours=None)

    assert repaired.missing == len(memory_ids) and repaired.indexed == len(memory_ids)
    assert repaired.complete and repaired.failed_accounts == 0
    assert _store().missing_ids(memory_ids) == []
    again = repair_entry_vectors(lookback_hours=24)
    assert again.scanned >= len(memory_ids) and again.missing == 0 and again.indexed == 0


def test_the_repair_sweep_leaves_memories_outside_its_lookback(client, embedder):
    from datetime import datetime, timedelta, timezone

    from thoughtpins.db import Memory
    from thoughtpins.memory.entry_vectors import repair_entry_vectors
    from thoughtpins.store import get_session

    _, headers = _sign_in(client, "vectors-lookback@thoughtpins.com")
    memory_ids = _memory_ids(_save_unindexed(client, headers, embedder))
    a_month_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
    with get_session() as session:
        session.query(Memory).filter(Memory.id.in_(memory_ids)).update(
            {Memory.created_at_utc: a_month_ago}, synchronize_session=False
        )
        session.commit()

    assert repair_entry_vectors(lookback_hours=72).indexed == 0
    assert repair_entry_vectors(lookback_hours=None).indexed == len(memory_ids)


def _record_upserts(monkeypatch) -> list[list[str]]:
    store = _store()
    real_add = store.add
    upserts: list[list[str]] = []

    def add(ids, *args, **kwargs):
        upserts.append(list(ids))
        real_add(ids, *args, **kwargs)

    monkeypatch.setattr(store, "add", add)
    return upserts


def test_an_entry_deleted_while_it_is_embedded_gets_no_vector(client, embedder, monkeypatch):
    from thoughtpins.memory.entry_vectors import index_entry_vectors

    user_id, headers = _sign_in(client, "vectors-delete-early@thoughtpins.com")
    entry_id = _save_unindexed(client, headers, embedder)
    memory_ids = _memory_ids(entry_id)
    upserts = _record_upserts(monkeypatch)

    embedder["before_return"] = lambda: client.delete(f"/v1/entries/{entry_id}", headers=headers)
    assert index_entry_vectors(entry_id, user_id) == 0

    assert upserts == [], "the deleted entry's text was sent to the index"
    assert _store().missing_ids(memory_ids) == memory_ids


def test_an_entry_deleted_just_before_the_upsert_has_its_vector_removed(client, embedder, monkeypatch):
    from thoughtpins.memory.entry_vectors import index_entry_vectors

    user_id, headers = _sign_in(client, "vectors-delete-late@thoughtpins.com")
    entry_id = _save_unindexed(client, headers, embedder)
    memory_ids = _memory_ids(entry_id)
    store = _store()
    real_add = store.add

    def add_after_the_deletion_committed(*args, **kwargs):
        # The deletion commits, then deletes vectors that do not exist yet.
        assert client.delete(f"/v1/entries/{entry_id}", headers=headers).status_code == 200
        real_add(*args, **kwargs)

    monkeypatch.setattr(store, "add", add_after_the_deletion_committed)

    assert index_entry_vectors(entry_id, user_id) == 0
    assert store.missing_ids(memory_ids) == memory_ids, "the deleted entry's text survived in the index"


def test_an_account_deleted_while_its_entry_is_embedded_gets_no_vector(client, embedder, monkeypatch):
    from thoughtpins.memory.entry_vectors import index_entry_vectors

    user_id, headers = _sign_in(client, "vectors-delete-account@thoughtpins.com")
    entry_id = _save_unindexed(client, headers, embedder)
    memory_ids = _memory_ids(entry_id)
    upserts = _record_upserts(monkeypatch)

    def delete_account() -> None:
        response = client.request("DELETE", "/v1/me", headers=headers, json={"confirm": "DELETE"})
        assert response.status_code == 200, response.text

    embedder["before_return"] = delete_account
    assert index_entry_vectors(entry_id, user_id) == 0

    assert upserts == [], "the deleted account's text was sent to the index"
    assert _store().missing_ids(memory_ids) == memory_ids


def test_the_upsert_runs_under_the_account_share_lock_and_the_provider_call_does_not(client, embedder, monkeypatch):
    """Account deletion takes the user row FOR UPDATE and deletes vectors before
    it commits. Holding FOR SHARE across the upsert makes it wait, then remove
    what was written. SQLite cannot show the wait, so this pins the order."""
    import thoughtpins.memory.entry_vectors as entry_vectors

    user_id, headers = _sign_in(client, "vectors-lock-order@thoughtpins.com")
    entry_id = _save_unindexed(client, headers, embedder)
    events: list[str] = []
    real_lock = entry_vectors.lock_active_user_for_write

    def lock(session, locked_user_id):
        events.append("lock")
        return real_lock(session, locked_user_id)

    monkeypatch.setattr(entry_vectors, "lock_active_user_for_write", lock)
    store = _store()
    real_add = store.add

    def upsert(*args, **kwargs) -> None:
        events.append("upsert")
        real_add(*args, **kwargs)

    monkeypatch.setattr(store, "add", upsert)
    embedder["before_return"] = lambda: events.append("embed")

    assert entry_vectors.index_entry_vectors(entry_id, user_id) == len(_memory_ids(entry_id))
    assert events == ["embed", "lock", "upsert"]


def test_a_scheduling_failure_never_fails_the_save(embedder, monkeypatch, loguru_lines):
    from thoughtpins.db import RawEntry
    from thoughtpins.ingestion.pipeline import process_message
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user

    def unavailable(user_id: str, entry_id: str) -> None:
        raise RuntimeError(f"broker refused {SENTINEL}")

    monkeypatch.setattr("thoughtpins.ingestion.pipeline.schedule_entry_vector_index", unavailable)
    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        result = process_message(session, ENTRY, user_id=user.id)
        assert result["type"] == "journal_stored"
        assert session.get(RawEntry, result["entry_id"]).processed_status == "completed"
    finally:
        session.close()
    rendered = "\n".join(loguru_lines)
    assert "left to the repair sweep (RuntimeError)" in rendered
    assert SENTINEL not in rendered


def test_the_celery_backend_queues_indexing_instead_of_running_it(embedder, monkeypatch):
    pytest.importorskip("celery")
    from thoughtpins.config import config

    monkeypatch.setattr(config, "CELERY_BROKER_URL", "memory://")
    monkeypatch.setattr(config, "CELERY_RESULT_BACKEND", "cache+memory://")
    import thoughtpins.worker as worker
    from thoughtpins.ingestion.pipeline import process_message
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user

    queued: list[tuple[str, str]] = []
    monkeypatch.setattr(
        worker, "enqueue_entry_vector_index", lambda entry_id, user_id: queued.append((entry_id, user_id))
    )
    for target in (config, type(config)):
        monkeypatch.setattr(target, "INGESTION_QUEUE_BACKEND", "celery")
    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        result = process_message(session, ENTRY, user_id=user.id)
        user_id = user.id
    finally:
        session.close()

    assert queued == [(result["entry_id"], user_id)]
    assert embedder["calls"] == 0, "the save itself must not wait on the embedding provider"


def test_storing_embeddings_raises_where_search_falls_back(embedder):
    from thoughtpins.memory.vector_store import VectorStore

    store = VectorStore()
    store._embedding_model = "llm_api"
    store._dimension = DIMENSION
    store._init_memory()
    embedder["fail"] = True

    with pytest.raises(ConnectionError):
        store.embed_documents(["a memory"])
    # Search degrades to a zero vector instead of failing the request.
    assert store._embed(["a query"]) == [[0.0] * DIMENSION]


def test_missing_ids_and_precomputed_vectors_on_local_qdrant(monkeypatch, tmp_path):
    pytest.importorskip("qdrant_client")
    from thoughtpins.config import config
    from thoughtpins.memory.vector_store import VectorStore

    for target in (config, type(config)):
        monkeypatch.setattr(target, "VECTOR_MODE", "qdrant_local")
        monkeypatch.setattr(target, "QDRANT_PATH", str(tmp_path / "qdrant"))
    monkeypatch.setattr(VectorStore, "_init_embedding_model", lambda self: setattr(self, "_dimension", 3))
    store = VectorStore()
    store.initialize()
    try:
        store.add(["kept"], ["a stored memory"], [{"user_id": "tenant"}], vectors=[[1.0, 0.0, 0.0]])

        assert store.missing_ids(["kept", "absent", "also-absent"]) == ["absent", "also-absent"]
        assert store.missing_ids([]) == []
        with pytest.raises(ValueError, match="vectors and ids"):
            store.add(["a", "b"], ["one", "two"], vectors=[[1.0, 0.0, 0.0]])
    finally:
        store.close()


def test_the_worker_queues_a_full_repair_at_start_and_recent_ones_on_an_interval(monkeypatch):
    pytest.importorskip("celery")
    from thoughtpins.config import config

    monkeypatch.setattr(config, "CELERY_BROKER_URL", "memory://")
    monkeypatch.setattr(config, "CELERY_RESULT_BACKEND", "cache+memory://")
    import thoughtpins.worker as worker

    sent: list[tuple[str, list]] = []
    clock = [1_000.0]
    monkeypatch.setattr(worker.celery_app, "send_task", lambda name, args, queue: sent.append((name, args)))
    monkeypatch.setattr(worker.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(worker, "_last_vector_repair_monotonic", 0.0)
    for target in (config, type(config)):
        monkeypatch.setattr(target, "VECTOR_INDEX_ON_INGEST", True)
        monkeypatch.setattr(target, "VECTOR_REPAIR_INTERVAL_SECONDS", 900)
        monkeypatch.setattr(target, "VECTOR_REPAIR_LOOKBACK_HOURS", 72)

    assert worker.dispatch_vector_repair_if_due(full=True)
    assert not worker.dispatch_vector_repair_if_due()
    clock[0] += 901
    assert worker.dispatch_vector_repair_if_due()
    assert sent == [("thoughtpins.repair_entry_vectors", [None]), ("thoughtpins.repair_entry_vectors", [72])]

    for target in (config, type(config)):
        monkeypatch.setattr(target, "VECTOR_REPAIR_INTERVAL_SECONDS", 0)
    assert not worker.dispatch_vector_repair_if_due(full=True)


def test_production_rejects_an_unbounded_repair_interval(monkeypatch) -> None:
    from thoughtpins.config import Config

    monkeypatch.setattr(Config, "ENVIRONMENT", "production")
    monkeypatch.setattr(Config, "VECTOR_REPAIR_INTERVAL_SECONDS", 5)
    monkeypatch.setattr(Config, "VECTOR_REPAIR_LOOKBACK_HOURS", 0)

    problems = Config.validate_startup()

    assert "VECTOR_REPAIR_INTERVAL_SECONDS must be 0 (off) or between 60 and 86400." in problems
    assert "VECTOR_REPAIR_LOOKBACK_HOURS must be at least 1." in problems
