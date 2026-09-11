from __future__ import annotations

from types import SimpleNamespace

import pytest


def _stub_embedding_model(store) -> None:
    store._embedding_model = "test"
    store._dimension = 3


def test_openai_embedding_provider_uses_configured_model(monkeypatch):
    from thoughtpins.config import config
    from thoughtpins.memory.vector_store import VectorStore

    config_cls = type(config)
    embedding_calls: list[dict] = []
    client_calls: list[dict] = []

    class FakeEmbeddings:
        def create(self, **kwargs):
            embedding_calls.append(kwargs)
            vectors = []
            for text in kwargs["input"]:
                if "beta" in text:
                    vectors.append([0.0, 1.0, 0.0])
                else:
                    vectors.append([1.0, 0.0, 0.0])
            return SimpleNamespace(data=[SimpleNamespace(embedding=vector) for vector in vectors])

    class FakeOpenAI:
        def __init__(self, **kwargs):
            client_calls.append(kwargs)
            self.embeddings = FakeEmbeddings()

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    for target in (config, config_cls):
        monkeypatch.setattr(target, "VECTOR_MODE", "memory")
        monkeypatch.setattr(target, "EMBEDDING_PROVIDER", "openai")
        monkeypatch.setattr(target, "OPENAI_API_KEY", "test-key")
        monkeypatch.setattr(target, "OPENAI_BASE_URL", "https://api.openai.com/v1")
        monkeypatch.setattr(target, "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        monkeypatch.setattr(target, "OPENAI_EMBEDDING_DIMENSIONS", 3)

    store = VectorStore()
    store.initialize()
    store.add(["alpha-memory", "beta-memory"], ["alpha quartz memory", "beta ledger memory"])

    results = store.search("alpha quartz", limit=1)

    assert results
    assert results[0]["id"] == "alpha-memory"
    assert client_calls[0]["api_key"] == "test-key"
    assert embedding_calls[0]["model"] == "text-embedding-3-small"
    assert embedding_calls[0]["dimensions"] == 3


def test_memory_vectors_enforce_tenant_scope_and_support_deletion(monkeypatch):
    from thoughtpins.memory.vector_store import VectorStore

    store = VectorStore()
    store._embedding_model = "test"
    store._dimension = 3
    store._init_memory()
    monkeypatch.setattr(
        store,
        "_embed",
        lambda texts: [[1.0, 0.0, 0.0] if "alpha" in text else [0.0, 1.0, 0.0] for text in texts],
    )
    store.add(
        ["tenant-a-memory", "tenant-b-memory"],
        ["alpha private marker", "alpha other marker"],
        [{"user_id": "tenant-a"}, {"user_id": "tenant-b"}],
    )

    scoped = store.search("alpha", limit=10, user_id="tenant-a")
    assert [item["id"] for item in scoped] == ["tenant-a-memory"]

    store.delete(["tenant-a-memory"])
    assert store.search("alpha", limit=10, user_id="tenant-a") == []
    assert [item["id"] for item in store.search("alpha", limit=10, user_id="tenant-b")] == ["tenant-b-memory"]


def test_remote_qdrant_uses_shared_authenticated_endpoint(monkeypatch) -> None:
    from thoughtpins.config import config
    from thoughtpins.memory.vector_store import VectorStore

    calls: list[dict] = []

    class FakeQdrantClient:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def get_collection(self, _name):
            return SimpleNamespace(config=SimpleNamespace(params=SimpleNamespace(vectors=None)))

        def close(self) -> None:
            pass

    config_cls = type(config)
    monkeypatch.setattr("qdrant_client.QdrantClient", FakeQdrantClient)
    for target in (config, config_cls):
        monkeypatch.setattr(target, "VECTOR_MODE", "qdrant_remote")
        monkeypatch.setattr(target, "QDRANT_URL", "https://vectors.example.test")
        monkeypatch.setattr(target, "QDRANT_API_KEY", "test-vector-key")
        monkeypatch.setattr(target, "QDRANT_TIMEOUT_SECONDS", 7)
    monkeypatch.setattr(
        VectorStore,
        "_init_embedding_model",
        _stub_embedding_model,
    )

    store = VectorStore()
    store.initialize()

    assert calls == [
        {
            "url": "https://vectors.example.test",
            "api_key": "test-vector-key",
            "timeout": 7,
        }
    ]
    assert store._qdrant_path is None


def test_remote_qdrant_initialization_fails_closed(monkeypatch) -> None:
    from thoughtpins.config import config
    from thoughtpins.memory.vector_store import VectorStore

    config_cls = type(config)
    for target in (config, config_cls):
        monkeypatch.setattr(target, "VECTOR_MODE", "qdrant_remote")
        monkeypatch.setattr(target, "QDRANT_URL", "https://vectors.example.test")
        monkeypatch.setattr(target, "QDRANT_API_KEY", "test-vector-key")
    monkeypatch.setattr("qdrant_client.QdrantClient", lambda **_kwargs: (_ for _ in ()).throw(OSError("offline")))
    monkeypatch.setattr(VectorStore, "_init_embedding_model", lambda self: None)

    with pytest.raises(RuntimeError, match="could not be initialized"):
        VectorStore().initialize()


def test_qdrant_deletion_cleans_every_owned_dimension_collection() -> None:
    from thoughtpins.memory.vector_store import VectorStore, _qdrant_point_id

    deleted: list[tuple[str, list[str]]] = []

    class FakeQdrantBackend:
        def get_collections(self):
            return SimpleNamespace(
                collections=[
                    SimpleNamespace(name="journal_memories_256"),
                    SimpleNamespace(name="journal_memories_1536"),
                    SimpleNamespace(name="unrelated_collection"),
                ]
            )

        def delete(self, *, collection_name, points_selector) -> None:
            deleted.append((collection_name, list(points_selector.points)))

    store = VectorStore()
    store._backend = FakeQdrantBackend()
    store._collection_name = "journal_memories_1536"

    store.delete(["memory-to-erase"])

    expected_point = _qdrant_point_id("memory-to-erase")
    assert deleted == [
        ("journal_memories_1536", [expected_point]),
        ("journal_memories_256", [expected_point]),
    ]


def test_faiss_deletion_rebuilds_only_retained_vectors() -> None:
    from thoughtpins.memory.vector_store import VectorStore

    class FakeFaissIndex:
        def __init__(self) -> None:
            self.reset_calls = 0
            self.added_rows = 0

        def reset(self) -> None:
            self.reset_calls += 1

        def add(self, values) -> None:
            self.added_rows += len(values)

    store = VectorStore()
    store._backend = "faiss"
    store._faiss_index = FakeFaissIndex()
    store._faiss_ids = ["remove-me", "keep-me"]
    store._faiss_texts = ["removed text", "retained text"]
    store._faiss_vectors = [[1.0, 0.0], [0.0, 1.0]]
    store._faiss_metadata = [{"user_id": "tenant-a"}, {"user_id": "tenant-b"}]

    store.delete(["remove-me"])

    assert store._faiss_ids == ["keep-me"]
    assert store._faiss_texts == ["retained text"]
    assert store._faiss_metadata == [{"user_id": "tenant-b"}]
    assert store._faiss_index.reset_calls == 1
    assert store._faiss_index.added_rows == 1


def test_qdrant_accepts_short_app_memory_ids(tmp_path, monkeypatch):
    import pytest

    pytest.importorskip("qdrant_client")

    from thoughtpins.config import config
    from thoughtpins.memory.vector_store import VectorStore

    config_cls = type(config)
    monkeypatch.setattr(config, "VECTOR_MODE", "qdrant_local")
    monkeypatch.setattr(config_cls, "VECTOR_MODE", "qdrant_local")
    monkeypatch.setattr(config, "QDRANT_PATH", str(tmp_path / "qdrant"))
    monkeypatch.setattr(config_cls, "QDRANT_PATH", str(tmp_path / "qdrant"))
    monkeypatch.setattr(
        VectorStore,
        "_init_embedding_model",
        _stub_embedding_model,
    )
    monkeypatch.setattr(VectorStore, "_embed", lambda self, texts: [[1.0, 0.0, 0.0] for _ in texts])

    store = VectorStore()
    try:
        store.initialize()
        store.add(
            ["abc123shortid", "othertenantid"],
            ["quartz compass marker", "quartz other tenant marker"],
            [{"user_id": "tenant-a"}, {"user_id": "tenant-b"}],
        )

        results = store.search("quartz compass", limit=2, user_id="tenant-a")

        assert [item["id"] for item in results] == ["abc123shortid"]
        assert "quartz compass marker" in results[0]["text"]

        store.delete(["abc123shortid"])
        assert store.search("quartz compass", limit=1, user_id="tenant-a") == []
        assert store.search("quartz compass", limit=1, user_id="tenant-b")[0]["id"] == "othertenantid"
    finally:
        store.close()


def test_qdrant_recreates_when_embedding_dimension_changes(tmp_path, monkeypatch):
    import pytest

    pytest.importorskip("qdrant_client")

    from thoughtpins.config import config
    from thoughtpins.memory.vector_store import VectorStore

    config_cls = type(config)
    monkeypatch.setattr(config, "VECTOR_MODE", "qdrant_local")
    monkeypatch.setattr(config_cls, "VECTOR_MODE", "qdrant_local")
    monkeypatch.setattr(config, "QDRANT_PATH", str(tmp_path / "qdrant"))
    monkeypatch.setattr(config_cls, "QDRANT_PATH", str(tmp_path / "qdrant"))
    monkeypatch.setattr(
        VectorStore,
        "_init_embedding_model",
        _stub_embedding_model,
    )
    monkeypatch.setattr(VectorStore, "_embed", lambda self, texts: [[1.0, 0.0, 0.0] for _ in texts])

    store = VectorStore()
    try:
        store.initialize()
        store.add(["old-memory"], ["old three dimensional memory"])

        monkeypatch.setattr(VectorStore, "_embed", lambda self, texts: [[0.0, 1.0, 0.0, 0.0] for _ in texts])
        store.add(["new-memory"], ["new four dimensional memory"])

        results = store.search("new four dimensional memory", limit=1)

        assert results
        assert results[0]["id"] == "new-memory"
    finally:
        store.close()
