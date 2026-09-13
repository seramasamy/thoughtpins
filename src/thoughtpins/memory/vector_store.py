"""VectorStore -- semantic search over embeddings using Qdrant local or FAISS fallback."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from thoughtpins.config import config
from thoughtpins.memory.qdrant_schema import ensure_remote_tenant_index

_QDRANT_ID_NAMESPACE = uuid.UUID("8dd1dce0-1de2-4bd0-9f70-8f21a2bdf8e2")


class VectorStore:
    """Abstract vector storage with pluggable backends."""

    def __init__(self):
        self._backend = None
        self._embedding_model = None
        self._collection_base_name = "journal_memories"
        self._collection_name = self._collection_base_name
        self._dimension = 384  # default for all-MiniLM-L6-v2
        self._qdrant_path: Path | None = None

    def initialize(self) -> None:
        mode = config.VECTOR_MODE
        self._init_embedding_model()

        if mode == "qdrant_local":
            self._init_qdrant(remote=False)
        elif mode == "qdrant_remote":
            self._init_qdrant(remote=True)
        elif mode == "faiss":
            self._init_faiss()
        elif mode == "chroma":
            self._init_chroma()
        elif mode == "memory":
            self._init_memory()
        else:
            raise ValueError(f"Unsupported vector mode: {mode}")

    def _init_embedding_model(self):
        provider = getattr(config, "EMBEDDING_PROVIDER", "llm")

        if provider == "llm":
            # Some OpenAI-compatible chat deployments do not expose embeddings; the
            # local fallback in the LLM client is 256-dimensional and is the safe
            # default until the first real vector confirms otherwise.
            self._embedding_model = "llm_api"
            self._dimension = 256
            logger.info("Using configured LLM embeddings (fallback-capable, dim={})", self._dimension)
            return

        if provider == "openai":
            self._embedding_model = "openai_api"
            self._dimension = _openai_configured_embedding_dimension()
            logger.info("Using configured hosted embeddings (dim={})", self._dimension)
            return

        if provider == "local":
            # Use local sentence-transformers model
            try:
                from sentence_transformers import SentenceTransformer

                self._embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
                dimension_reader = getattr(self._embedding_model, "get_embedding_dimension", None)
                if dimension_reader is None:
                    dimension_reader = self._embedding_model.get_sentence_embedding_dimension
                self._dimension = int(dimension_reader())
                logger.info("Loaded local embedding runtime (dim={})", self._dimension)
                return
            except Exception as e:
                logger.warning(
                    "Could not load local embedding runtime: {}. Falling back to configured embeddings.", str(e)[:160]
                )

        # Fallback: configured OpenAI-compatible LLM embedding API
        self._embedding_model = "llm_api"
        self._dimension = 256
        logger.info("Using configured LLM embeddings (fallback, dim={})", self._dimension)

    def _init_qdrant(self, *, remote: bool) -> None:
        try:
            from qdrant_client import QdrantClient

            self._set_qdrant_collection_for_dimension()
            if remote:
                if not config.QDRANT_URL:
                    raise RuntimeError("QDRANT_URL is required for qdrant_remote")
                self._backend = QdrantClient(
                    url=config.QDRANT_URL,
                    api_key=config.QDRANT_API_KEY or None,
                    timeout=config.QDRANT_TIMEOUT_SECONDS,
                )
            else:
                _prepare_qdrant_sqlite_thread_setting()
                qdrant_path = config.qdrant_path()
                self._qdrant_path = qdrant_path
                qdrant_path.mkdir(parents=True, exist_ok=True)
                self._backend = QdrantClient(path=str(qdrant_path))

            try:
                info = self._backend.get_collection(self._collection_name)
            except Exception:
                self._create_qdrant_collection()
            else:
                existing_size = _qdrant_vector_size(info)
                if existing_size and existing_size != self._dimension:
                    if config.is_production():
                        raise RuntimeError(
                            "Qdrant collection dimension does not match the configured embedding dimension; run a controlled reindex"
                        )
                    logger.warning(
                        "Qdrant collection '{}' has vector dim {}, expected {}; recreating derived index",
                        self._collection_name,
                        existing_size,
                        self._dimension,
                    )
                    self._recreate_qdrant_collection()
                else:
                    logger.debug("Qdrant collection '{}' already exists", self._collection_name)
            ensure_remote_tenant_index(self._backend, self._collection_name, remote=remote)
            logger.info("Qdrant {} vector store ready", "remote" if remote else "local")
        except ImportError as exc:
            if remote or config.is_production():
                raise RuntimeError("qdrant-client is required for the configured vector backend") from exc
            logger.warning("qdrant-client not installed, falling back to FAISS")
            self._init_faiss()
        except Exception as e:
            if remote or config.is_production():
                raise RuntimeError("Configured Qdrant backend could not be initialized") from e
            logger.error("Qdrant init failed: {}. Falling back to FAISS.", e)
            self._init_faiss()

    def _create_qdrant_collection(self) -> None:
        from qdrant_client.models import Distance, VectorParams

        backend = self._require_object_backend()
        backend.create_collection(
            collection_name=self._collection_name,
            vectors_config=VectorParams(size=self._dimension, distance=Distance.COSINE),
        )
        ensure_remote_tenant_index(backend, self._collection_name, remote=self._qdrant_path is None)
        logger.info("Created Qdrant collection '{}'", self._collection_name)

    def _recreate_qdrant_collection(self) -> None:
        self._set_qdrant_collection_for_dimension()
        self._reset_qdrant_client()
        backend = self._require_object_backend()
        for collection_name in self._qdrant_collection_names():
            backend.delete_collection(collection_name=collection_name)
        self._create_qdrant_collection()
        self._reset_qdrant_client()

    def _qdrant_collection_names(self) -> list[str]:
        """Return every derived collection owned by this application."""
        backend = self._require_object_backend()
        list_collections = getattr(backend, "get_collections", None)
        if list_collections is None:
            return [self._collection_name]
        response = list_collections()
        collections = getattr(response, "collections", response)
        names = {
            str(getattr(collection, "name", collection))
            for collection in (collections or [])
            if str(getattr(collection, "name", collection)).startswith(f"{self._collection_base_name}_")
        }
        names.add(self._collection_name)
        return sorted(names)

    def _set_qdrant_collection_for_dimension(self) -> None:
        self._collection_name = _qdrant_collection_name(self._collection_base_name, self._dimension)

    def _reset_qdrant_client(self) -> None:
        if self._qdrant_path is None:
            return
        _close_qdrant_backend(self._backend)
        from qdrant_client import QdrantClient

        _prepare_qdrant_sqlite_thread_setting()
        self._backend = QdrantClient(path=str(self._qdrant_path))

    def _init_faiss(self):
        try:
            import faiss

            self._faiss_index = faiss.IndexFlatIP(self._dimension)
            self._faiss_ids: list[str] = []
            self._faiss_texts: list[str] = []
            self._faiss_vectors: list[list[float]] = []
            self._faiss_metadata: list[dict[str, Any]] = []
            self._backend = "faiss"
            logger.info("FAISS vector store ready (dim={})", self._dimension)
        except ImportError:
            logger.warning("faiss not installed, using in-memory fallback")
            self._init_memory()

    def _init_chroma(self):
        try:
            import chromadb

            self._backend = chromadb.PersistentClient(path=str(config.resolve_path("./data/chroma")))
            self._collection = self._backend.get_or_create_collection(
                name=self._collection_name,
            )
            logger.info("Chroma vector store ready")
        except ImportError:
            logger.warning("chromadb not installed, falling back to FAISS")
            self._init_faiss()

    def _init_memory(self):
        self._inmemory_vectors: list[tuple[list[float], str, str, dict[str, Any]]] = []
        self._backend = "memory"

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if self._embedding_model is None:
            return [[0.0] * self._dimension for _ in texts]

        if self._embedding_model == "llm_api":
            # Use the configured OpenAI-compatible API for embeddings.
            from thoughtpins.llm.client import get_embeddings

            try:
                return get_embeddings(texts)
            except Exception as e:
                logger.warning("Configured LLM embedding failed: {}, using zero vectors", e)
                return [[0.0] * self._dimension for _ in texts]

        if self._embedding_model == "openai_api":
            try:
                return _embed_openai(texts)
            except Exception as e:
                logger.warning("OpenAI embedding failed: {}, using zero vectors", e)
                return [[0.0] * self._dimension for _ in texts]

        # Local sentence-transformers model
        embeddings = self._embedding_model.encode(texts, show_progress_bar=False)
        return embeddings.tolist()

    def add(self, ids: list[str], texts: list[str], metadata: list[dict] | None = None) -> None:
        if not texts:
            return
        if len(ids) != len(texts):
            raise ValueError("ids and texts must have the same length")
        if metadata is not None and len(metadata) != len(ids):
            raise ValueError("metadata and ids must have the same length")
        vectors = self._embed(texts)
        self._sync_dimension_from_vectors(vectors)
        metadatas = [dict(item) for item in (metadata or [{}] * len(ids))]

        if hasattr(self, "_faiss_index"):
            import numpy as np

            arr = np.array(vectors, dtype=np.float32)
            self._faiss_index.add(arr)
            self._faiss_ids.extend(ids)
            self._faiss_texts.extend(texts)
            self._faiss_vectors.extend(vectors)
            self._faiss_metadata.extend(metadatas)
        elif isinstance(self._backend, str) and self._backend == "memory":
            for vec, tid, txt, meta in zip(vectors, ids, texts, metadatas, strict=True):
                self._inmemory_vectors.append((vec, tid, txt, meta))
        elif hasattr(self, "_collection"):
            self._collection.add(
                ids=ids,
                embeddings=vectors,
                documents=texts,
                metadatas=metadatas,
            )
        else:
            # Qdrant
            from qdrant_client.models import PointStruct

            backend = self._require_object_backend()
            points = [
                PointStruct(
                    id=_qdrant_point_id(tid),
                    vector=vec,
                    payload={**meta, "external_id": tid, "text": txt},
                )
                for tid, vec, txt, meta in zip(ids, vectors, texts, metadatas, strict=True)
            ]
            try:
                backend.upsert(collection_name=self._collection_name, points=points)
            except Exception as exc:
                if not _looks_like_dimension_error(exc):
                    raise
                actual_dim = _vector_dimension(vectors)
                if actual_dim:
                    self._dimension = actual_dim
                logger.warning(
                    "Qdrant upsert saw vector dimension drift; recreating '{}' at dim {} and retrying",
                    self._collection_name,
                    self._dimension,
                )
                self._recreate_qdrant_collection()
                self._require_object_backend().upsert(collection_name=self._collection_name, points=points)

    def search(self, query: str, limit: int = 10, *, user_id: str | None = None) -> list[dict]:
        """Search the derived index, optionally enforcing its tenant boundary.

        SQL remains the source of truth, but filtering at the vector layer keeps
        another tenant's text out of candidate generation and avoids noisy
        cross-tenant nearest neighbours.
        """
        if not query:
            return []
        query_vec = self._embed([query])[0]
        self._sync_dimension_from_vectors([query_vec])

        if hasattr(self, "_faiss_index"):
            import numpy as np

            arr = np.array([query_vec], dtype=np.float32)
            candidate_count = len(self._faiss_ids) if user_id else min(limit, len(self._faiss_ids))
            if candidate_count == 0:
                return []
            scores, indices = self._faiss_index.search(arr, candidate_count)
            results = []
            for score, idx in zip(scores[0], indices[0], strict=True):
                if idx >= 0 and idx < len(self._faiss_ids):
                    if user_id and self._faiss_metadata[idx].get("user_id") != user_id:
                        continue
                    results.append(
                        {
                            "id": self._faiss_ids[idx],
                            "text": self._faiss_texts[idx],
                            "score": float(score),
                        }
                    )
                    if len(results) >= limit:
                        break
            return results
        elif isinstance(self._backend, str) and self._backend == "memory":
            # Simple cosine similarity
            results = []
            for vec, tid, txt, meta in self._inmemory_vectors:
                if user_id and meta.get("user_id") != user_id:
                    continue
                sim = _cosine_sim(query_vec, vec)
                results.append({"id": tid, "text": txt, "score": sim})
            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:limit]
        elif hasattr(self, "_collection"):
            query_options: dict[str, Any] = {"query_embeddings": [query_vec], "n_results": limit}
            if user_id:
                query_options["where"] = {"user_id": user_id}
            chroma_results = self._collection.query(**query_options)
            return [
                {"id": rid, "text": rdoc, "score": 1.0 - (dist if dist else 0)}
                for rid, rdoc, dist in zip(
                    chroma_results["ids"][0],
                    chroma_results["documents"][0]
                    if chroma_results.get("documents")
                    else [""] * len(chroma_results["ids"][0]),
                    chroma_results.get("distances", [[0]] * len(chroma_results["ids"][0]))[0],
                    strict=True,
                )
            ]
        else:
            # Qdrant
            backend = self._require_object_backend()
            query_filter = None
            if user_id:
                from qdrant_client.models import FieldCondition, Filter, MatchValue

                query_filter = Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))])
            if hasattr(backend, "search"):
                results = backend.search(
                    collection_name=self._collection_name,
                    query_vector=query_vec,
                    limit=limit,
                    query_filter=query_filter,
                )
            else:
                response = backend.query_points(
                    collection_name=self._collection_name,
                    query=query_vec,
                    limit=limit,
                    with_payload=True,
                    query_filter=query_filter,
                )
                results = getattr(response, "points", response)
            return [
                {
                    "id": (r.payload or {}).get("external_id") or str(r.id),
                    "text": (r.payload or {}).get("text", ""),
                    "score": float(r.score),
                }
                for r in results
            ]

    def delete(self, ids: list[str]) -> None:
        if not ids:
            return
        deleted = set(ids)
        if hasattr(self, "_faiss_index"):
            retained = [
                (tid, text, vector, metadata)
                for tid, text, vector, metadata in zip(
                    self._faiss_ids,
                    self._faiss_texts,
                    self._faiss_vectors,
                    self._faiss_metadata,
                    strict=True,
                )
                if tid not in deleted
            ]
            self._faiss_index.reset()
            self._faiss_ids = [item[0] for item in retained]
            self._faiss_texts = [item[1] for item in retained]
            self._faiss_vectors = [item[2] for item in retained]
            self._faiss_metadata = [item[3] for item in retained]
            if self._faiss_vectors:
                import numpy as np

                self._faiss_index.add(np.array(self._faiss_vectors, dtype=np.float32))
        elif isinstance(self._backend, str) and self._backend == "memory":
            self._inmemory_vectors = [item for item in self._inmemory_vectors if item[1] not in deleted]
        elif hasattr(self, "_collection"):
            self._collection.delete(ids=ids)
        elif self._backend is not None and not isinstance(self._backend, str):
            from qdrant_client.models import PointIdsList

            point_ids = PointIdsList(points=[_qdrant_point_id(pid) for pid in ids])
            for collection_name in self._qdrant_collection_names():
                self._backend.delete(
                    collection_name=collection_name,
                    points_selector=point_ids,
                )

    def reset(self) -> None:
        """Clear the derived vector index for the active backend."""
        if hasattr(self, "_faiss_index"):
            self._init_faiss()
        elif isinstance(self._backend, str) and self._backend == "memory":
            self._inmemory_vectors.clear()
        elif hasattr(self, "_collection"):
            backend = self._require_object_backend()
            try:
                backend.delete_collection(name=self._collection_name)
            except Exception:
                logger.debug("Chroma collection delete skipped during reset", exc_info=True)
            self._collection = backend.get_or_create_collection(name=self._collection_name)
        elif self._backend is not None:
            self._recreate_qdrant_collection()

    def count(self) -> int:
        if hasattr(self, "_faiss_index"):
            return self._faiss_index.ntotal
        elif isinstance(self._backend, str) and self._backend == "memory":
            return len(self._inmemory_vectors)
        elif hasattr(self, "_collection"):
            return self._collection.count()
        elif self._backend is not None:
            info = self._backend.get_collection(self._collection_name)
            return info.points_count
        return 0

    def close(self) -> None:
        backend = self._backend
        if backend is not None and not isinstance(backend, str):
            if self._is_qdrant_backend():
                _close_qdrant_backend(backend)
            elif hasattr(backend, "close"):
                try:
                    backend.close()
                except Exception:
                    logger.debug("Vector backend close failed", exc_info=True)
        self._backend = None

    def _sync_dimension_from_vectors(self, vectors: list[list[float]]) -> None:
        actual_dim = _vector_dimension(vectors)
        if not actual_dim or actual_dim == self._dimension:
            return

        previous_dim = self._dimension
        if config.is_production():
            raise RuntimeError(
                f"Embedding dimension changed from {previous_dim} to {actual_dim}; run a controlled vector reindex"
            )
        self._dimension = actual_dim
        logger.warning(
            "Embedding dimension changed from {} to {}; resetting derived vector index",
            previous_dim,
            actual_dim,
        )
        if self._is_qdrant_backend():
            self._recreate_qdrant_collection()
        elif hasattr(self, "_faiss_index"):
            self._init_faiss()

    def _is_qdrant_backend(self) -> bool:
        return (
            self._backend is not None
            and not isinstance(self._backend, str)
            and not hasattr(self, "_collection")
            and not hasattr(self, "_faiss_index")
        )

    def _require_object_backend(self) -> Any:
        backend = self._backend
        if backend is None or isinstance(backend, str):
            raise RuntimeError("Vector backend is not initialized")
        return backend


def _prepare_qdrant_sqlite_thread_setting() -> None:
    """Avoid qdrant-client's local sqlite probe leaving an unclosed temp connection."""
    try:
        from qdrant_client.local.persistence import CollectionPersistence
    except Exception:
        return
    if CollectionPersistence.CHECK_SAME_THREAD is not None:
        return

    import sqlite3

    tmp_conn = sqlite3.connect(":memory:")
    try:
        threadsafe = tmp_conn.execute(
            "select * from pragma_compile_options where compile_options like 'THREADSAFE=%'"
        ).fetchone()[0]
    finally:
        tmp_conn.close()
    CollectionPersistence.CHECK_SAME_THREAD = threadsafe != "THREADSAFE=1"


def _close_qdrant_backend(backend: object | None) -> None:
    """Close Qdrant local storage and drop sqlite-backed collection references."""
    if backend is None or isinstance(backend, str):
        return
    try:
        if hasattr(backend, "close"):
            backend.close()
        local_client = getattr(backend, "_client", None)
        collections = getattr(local_client, "collections", None)
        if isinstance(collections, dict):
            collections.clear()
    except Exception:
        logger.debug("Qdrant backend close failed", exc_info=True)


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _qdrant_point_id(external_id: str) -> str:
    """Map app-level memory IDs to stable Qdrant-compatible UUID point IDs."""
    return str(uuid.uuid5(_QDRANT_ID_NAMESPACE, external_id))


def _qdrant_collection_name(base_name: str, dimension: int) -> str:
    return f"{base_name}_{dimension}"


def _qdrant_vector_size(collection_info) -> int | None:
    try:
        vectors = collection_info.config.params.vectors
    except AttributeError:
        return None
    if isinstance(vectors, dict):
        first = next(iter(vectors.values()), None)
        return getattr(first, "size", None)
    return getattr(vectors, "size", None)


def _vector_dimension(vectors: list[list[float]]) -> int | None:
    if not vectors or not vectors[0]:
        return None
    return len(vectors[0])


def _looks_like_dimension_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(fragment in message for fragment in ("dimension", "broadcast", "shape"))


def _openai_configured_embedding_dimension() -> int:
    configured = getattr(config, "OPENAI_EMBEDDING_DIMENSIONS", 1536)
    if configured > 0:
        return configured
    model = getattr(config, "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    if model == "text-embedding-3-large":
        return 3072
    return 1536


def _openai_model_supports_dimensions(model: str) -> bool:
    return model.startswith("text-embedding-3")


def _embed_openai(texts: list[str]) -> list[list[float]]:
    from openai import OpenAI

    from thoughtpins.tenancy import get_current_tenant_id
    from thoughtpins.usage import ensure_budget_available, record_llm_usage

    if not getattr(config, "OPENAI_API_KEY", ""):
        raise RuntimeError("OPENAI_API_KEY is required for EMBEDDING_PROVIDER=openai")

    # This is a separate billed path from the LLM client's embed(); it must be
    # metered here or hosted-embedding spend goes untracked entirely.
    tenant_id = get_current_tenant_id()
    ensure_budget_available(tenant_id)

    client = OpenAI(
        api_key=config.OPENAI_API_KEY,
        base_url=config.OPENAI_BASE_URL,
        timeout=max(5, config.LLM_TIMEOUT_SECONDS),
        max_retries=max(0, config.LLM_MAX_RETRIES),
    )
    kwargs: dict[str, object] = {
        "model": config.OPENAI_EMBEDDING_MODEL,
        "input": texts,
    }
    dimensions = getattr(config, "OPENAI_EMBEDDING_DIMENSIONS", 1536)
    if dimensions > 0 and _openai_model_supports_dimensions(config.OPENAI_EMBEDDING_MODEL):
        kwargs["dimensions"] = dimensions
    response = client.embeddings.create(**kwargs)
    usage = getattr(response, "usage", None)
    if usage is not None:
        record_llm_usage(
            user_id=tenant_id,
            provider="openai",
            model=getattr(response, "model", "") or config.OPENAI_EMBEDDING_MODEL,
            operation="embedding",
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        )
    return [list(item.embedding) for item in response.data]


# Singleton
import threading

_vector_store: Optional[VectorStore] = None
_vs_lock = threading.Lock()


def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        with _vs_lock:
            if _vector_store is None:
                _vector_store = VectorStore()
                _vector_store.initialize()
    return _vector_store


def close_vector_store() -> None:
    global _vector_store
    if _vector_store is not None:
        _vector_store.close()
        _vector_store = None
