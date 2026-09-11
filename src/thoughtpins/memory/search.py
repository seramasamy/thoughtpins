"""Hybrid search orchestration across SQL, vectors, documents, and graph evidence.

Candidate generation only. Eight available channels propose memories, their
proposals are merged by identity, and :mod:`thoughtpins.memory.ranking` decides
the order. Keeping generation and ordering apart is what lets an evaluation
replay one candidate pool under several ranking policies.

Two properties this module is responsible for:

*Degradation.* A channel is an optimisation, not a dependency. Any one of them
failing — an unreachable vector service, a graph query that times out — costs
recall for that query and nothing else. The alternative, which this file used
to implement, was that a single unavailable provider raised through the whole
search.

*Determinism.* The same corpus and query must produce the same candidate
identities on every process and every run, or an evaluation cannot compare two
runs and a cache cannot be keyed on them.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from hashlib import blake2b

from loguru import logger
from sqlalchemy.orm import Session

from thoughtpins.config import config
from thoughtpins.db import Memory
from thoughtpins.memory.ranking import DEFAULT_RANKING_POLICY, RankingPolicy, rerank_results
from thoughtpins.memory.search_analysis import _clean_query
from thoughtpins.memory.search_support import (
    _add_source,
    _attach_user_importance,
    _document_title_search,
    _graph_memory_expansion,
    _mem_to_result,
    _memory_query,
    _merge_result,
    _raw_entry_search,
    _token_search_memories,
    graph_search_hits,
)
from thoughtpins.memory.search_types import SearchResult
from thoughtpins.memory.store import MemoryStore
from thoughtpins.memory.vector_store import get_vector_store
from thoughtpins.store import get_session

__all__ = ["SearchResult", "graph_search_hits", "search"]

# An exact substring match on a short query is noise: "the" matches almost
# everything and tells the ranker nothing.
_MIN_EXACT_PHRASE_CHARS = 4

# Scores asserted by channels that match structurally rather than semantically.
# Both are starting points the ranker recalibrates; neither survives to output.
_ENTITY_FILTER_SCORE = 0.8
_EXACT_PHRASE_SCORE = 0.95
_VECTOR_FALLBACK_SCORE = 0.5

# The keyword channel is cheap and high-recall, so it is given a wider net than
# the others and allowed to contribute more candidates for the ranker to sift.
_KEYWORD_CANDIDATE_MULTIPLIER = 3

_EVIDENCE_SNIPPET_CHARS = 1200


def _stable_key(prefix: str, text: str) -> str:
    """A candidate identity that survives a process restart.

    Python's ``hash()`` is randomised per process for str, so using it here
    meant graph evidence carried a different identity in the API than in the
    worker, and a different one again on the next run. That silently breaks
    replaying an evaluation and any cache keyed on a candidate.
    """
    digest = blake2b(text.encode("utf-8"), digest_size=8).hexdigest()
    return f"{prefix}:{digest}"


@contextmanager
def _search_session(session: Session | None) -> Iterator[Session]:
    """Yield a session, closing it only if this call opened it.

    Previously the close happened on the success path alone, so any channel
    raising leaked the connection. Searches run per request and per background
    job, so a leak here exhausts the pool under exactly the load that matters.
    """
    if session is not None:
        yield session
        return
    owned = get_session()
    try:
        yield owned
    finally:
        owned.close()


def _channel(name: str) -> Callable[[Callable[[], None]], None]:
    """Run one candidate channel, absorbing its failure.

    Returning fewer candidates is a worse answer. Raising is no answer at all,
    and a hybrid retriever that cannot lose a channel is not really hybrid.
    """

    def run(collect: Callable[[], None]) -> None:
        try:
            collect()
        except Exception as exc:  # noqa: BLE001 - a channel must not fail the query
            logger.warning("Retrieval channel {} unavailable: {}", name, exc)

    return run


def search(
    query: str,
    *,
    session: Session | None = None,
    user_id: str | None = None,
    entity_filter: str | None = None,
    include_private: bool = False,
    limit: int = 20,
    ranking_policy: RankingPolicy = DEFAULT_RANKING_POLICY,
) -> list[SearchResult]:
    """Search memories inside an optional user scope."""
    with _search_session(session) as active:
        results: dict[str, SearchResult] = {}

        if entity_filter:
            _channel("entity_filter")(
                lambda: _collect_entity_filter(
                    active, results, entity_filter, user_id=user_id, include_private=include_private, limit=limit
                )
            )
        _channel("exact_phrase")(
            lambda: _collect_exact_phrase(
                active, results, query, user_id=user_id, include_private=include_private, limit=limit
            )
        )
        _channel("vector")(
            lambda: _collect_vector(
                active, results, query, user_id=user_id, include_private=include_private, limit=limit
            )
        )
        _channel("keyword")(
            lambda: _collect_keyword(
                active, results, query, user_id=user_id, include_private=include_private, limit=limit
            )
        )
        _channel("sql_graph")(
            lambda: _collect_graph_expansion(active, results, query, user_id=user_id, include_private=include_private)
        )
        _channel("document_title")(
            lambda: _collect_document_titles(active, results, query, user_id=user_id, limit=limit)
        )
        _channel("raw_keyword")(
            lambda: _collect_raw_entries(
                active, results, query, user_id=user_id, include_private=include_private, limit=limit
            )
        )
        _channel("graph_evidence")(
            lambda: _collect_graph_evidence(active, results, query, user_id=user_id, limit=limit)
        )

        candidates = list(results.values())
        _attach_user_importance(active, candidates, user_id=user_id)
        return rerank_results(candidates, query=query, limit=limit, policy=ranking_policy)


# --------------------------------------------------------------------- channels
#
# Each collector mutates the shared candidate map. They are separate functions
# so a channel can be exercised, disabled, or timed on its own, and so the
# orchestration above reads as the list of evidence sources it actually is.


def _collect_entity_filter(
    session: Session,
    results: dict[str, SearchResult],
    entity_filter: str,
    *,
    user_id: str | None,
    include_private: bool,
    limit: int,
) -> None:
    """Memories attached to a named entity, newest first."""
    entity_ids = [entity.id for entity in MemoryStore(session, user_id=user_id).find_entities(entity_filter)]
    if not entity_ids:
        return
    query = (
        _memory_query(session, user_id=user_id, include_private=include_private)
        .filter((Memory.subject_entity_id.in_(entity_ids)) | (Memory.object_entity_id.in_(entity_ids)))
        .order_by(Memory.local_date.desc())
        .limit(limit)
    )
    for rank, memory in enumerate(query.all(), start=1):
        _merge_result(results, _mem_to_result(memory, score=_ENTITY_FILTER_SCORE, source="entity_filter", rank=rank))


def _collect_exact_phrase(
    session: Session,
    results: dict[str, SearchResult],
    query: str,
    *,
    user_id: str | None,
    include_private: bool,
    limit: int,
) -> None:
    """Literal substring match, which vectors reliably miss on rare names."""
    exact = _clean_query(query)
    if not exact or len(exact) < _MIN_EXACT_PHRASE_CHARS:
        return
    matches = (
        _memory_query(session, user_id=user_id, include_private=include_private)
        .filter(Memory.text.ilike(f"%{exact}%"))
        .limit(limit)
        .all()
    )
    for rank, memory in enumerate(matches, start=1):
        _merge_result(results, _mem_to_result(memory, score=_EXACT_PHRASE_SCORE, source="exact_phrase", rank=rank))


def _collect_vector(
    session: Session,
    results: dict[str, SearchResult],
    query: str,
    *,
    user_id: str | None,
    include_private: bool,
    limit: int,
) -> None:
    """Semantic neighbours, re-read from SQL so tenant scoping still applies."""
    for rank, hit in enumerate(get_vector_store().search(query, limit=limit, user_id=user_id), start=1):
        memory_id = hit["id"]
        score = hit.get("score", _VECTOR_FALLBACK_SCORE)
        if memory_id in results:
            results[memory_id].score = max(results[memory_id].score, score)
            _add_source(results[memory_id], "vector", rank=rank)
            continue
        # The vector index is derived state; SQL decides what this tenant may
        # actually see, so a hit is only admitted if the scoped query returns it.
        memory = (
            _memory_query(session, user_id=user_id, include_private=include_private)
            .filter(Memory.id == memory_id)
            .first()
        )
        if memory:
            _merge_result(results, _mem_to_result(memory, score=score, source="vector", rank=rank))


def _collect_keyword(
    session: Session,
    results: dict[str, SearchResult],
    query: str,
    *,
    user_id: str | None,
    include_private: bool,
    limit: int,
) -> None:
    """Lexical scoring over memory text."""
    hits = _token_search_memories(
        session,
        query,
        user_id=user_id,
        include_private=include_private,
        limit=limit * _KEYWORD_CANDIDATE_MULTIPLIER,
    )
    for rank, (memory, score) in enumerate(hits, start=1):
        if memory.id in results:
            results[memory.id].score = max(results[memory.id].score, score)
            _add_source(results[memory.id], "keyword", rank=rank)
        else:
            _merge_result(results, _mem_to_result(memory, score=score, source="keyword", rank=rank))


def _collect_graph_expansion(
    session: Session,
    results: dict[str, SearchResult],
    query: str,
    *,
    user_id: str | None,
    include_private: bool,
) -> None:
    """Memories reached by walking relationships out from matched entities."""
    hits = _graph_memory_expansion(
        session,
        query,
        user_id=user_id,
        include_private=include_private,
        limit=config.MEMORY_HYBRID_GRAPH_RESULTS,
    )
    for rank, (memory, score) in enumerate(hits, start=1):
        _merge_result(results, _mem_to_result(memory, score=score, source="sql_graph", rank=rank))


def _collect_document_titles(
    session: Session,
    results: dict[str, SearchResult],
    query: str,
    *,
    user_id: str | None,
    limit: int,
) -> None:
    """Saved sources matched on title, so "that article about X" resolves."""
    for rank, (source, score) in enumerate(
        _document_title_search(session, query, user_id=user_id, limit=limit), start=1
    ):
        key = f"source:{source.id}"
        existing = results.get(key)
        if existing is not None:
            _add_source(existing, "document_title", rank=rank)
            continue
        results[key] = SearchResult(
            memory_id=key,
            text=f"Source: {source.title}. Summary: {source.summary or ''}".strip(),
            memory_type="document_source",
            local_date=str(source.local_date) if source.local_date else "",
            confidence="observed_by_user",
            sensitivity=source.sensitivity or "personal",
            source_entry_id=source.raw_entry_id,
            score=score,
            source_kind="document",
            source_title=source.title,
            evidence_text=source.summary or source.raw_text[:_EVIDENCE_SNIPPET_CHARS],
            retrieval_sources=["document_title"],
            source_ranks={"document_title": rank},
        )


def _collect_raw_entries(
    session: Session,
    results: dict[str, SearchResult],
    query: str,
    *,
    user_id: str | None,
    include_private: bool,
    limit: int,
) -> None:
    """The entry as written, for questions extraction did not anticipate."""
    hits = _raw_entry_search(session, query, user_id=user_id, include_private=include_private, limit=limit)
    for rank, (entry, score) in enumerate(hits, start=1):
        key = f"raw:{entry.id}"
        existing = results.get(key)
        if existing is not None:
            _add_source(existing, "raw_keyword", rank=rank)
            continue
        snippet = entry.raw_text[:_EVIDENCE_SNIPPET_CHARS]
        results[key] = SearchResult(
            memory_id=key,
            text=snippet,
            memory_type="raw_entry",
            local_date=str(entry.local_date) if entry.local_date else "",
            confidence="observed_by_user",
            sensitivity=entry.sensitivity,
            source_entry_id=entry.id,
            score=score,
            source_kind=entry.source or "journal",
            evidence_text=snippet,
            retrieval_sources=["raw_keyword"],
            source_ranks={"raw_keyword": rank},
        )


def _collect_graph_evidence(
    session: Session,
    results: dict[str, SearchResult],
    query: str,
    *,
    user_id: str | None,
    limit: int,
) -> None:
    """Relationship facts, which carry no row of their own to key on."""
    hits = graph_search_hits(session, query, user_id=user_id, limit=max(5, limit // 2))
    for rank, hit in enumerate(hits, start=1):
        key = _stable_key("graph", hit.text)
        existing = results.get(key)
        if existing is not None:
            _add_source(existing, hit.source, rank=rank)
            continue
        results[key] = SearchResult(
            memory_id=key,
            text=hit.text,
            memory_type="graph_evidence",
            local_date="",
            confidence="observed_by_user",
            sensitivity="personal",
            source_entry_id=str(hit.metadata.get("raw_entry_id") or ""),
            score=hit.score,
            entity_names=hit.entity_names,
            source_kind=hit.source,
            evidence_text=hit.text,
            retrieval_sources=[hit.source],
            source_ranks={hit.source: rank},
        )
