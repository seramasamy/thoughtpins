"""Hybrid search orchestration across SQL, vectors, documents, and graph evidence."""

from __future__ import annotations

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
    owned_session = session is None
    if session is None:
        session = get_session()
    store = MemoryStore(session, user_id=user_id)

    results: dict[str, SearchResult] = {}

    if entity_filter:
        entities = store.find_entities(entity_filter)
        entity_ids = [e.id for e in entities]
        if entity_ids:
            memory_q = _memory_query(session, user_id=user_id, include_private=include_private).filter(
                (Memory.subject_entity_id.in_(entity_ids)) | (Memory.object_entity_id.in_(entity_ids))
            )
            memories = memory_q.order_by(Memory.local_date.desc()).limit(limit).all()
            for rank, memory in enumerate(memories, start=1):
                _merge_result(results, _mem_to_result(memory, score=0.8, source="entity_filter", rank=rank))

    exact_query = _clean_query(query)
    if exact_query and len(exact_query) >= 4:
        text_q = _memory_query(session, user_id=user_id, include_private=include_private).filter(
            Memory.text.ilike(f"%{exact_query}%")
        )
        for rank, memory in enumerate(text_q.limit(limit).all(), start=1):
            _merge_result(results, _mem_to_result(memory, score=0.95, source="exact_phrase", rank=rank))

    try:
        vector_results = get_vector_store().search(query, limit=limit, user_id=user_id)
        for rank, vector_result in enumerate(vector_results, start=1):
            mem_id = vector_result["id"]
            if mem_id in results:
                results[mem_id].score = max(results[mem_id].score, vector_result.get("score", 0.5))
                _add_source(results[mem_id], "vector", rank=rank)
                continue
            memory_q = _memory_query(session, user_id=user_id, include_private=include_private).filter(
                Memory.id == mem_id
            )
            memory = memory_q.first()
            if memory:
                _merge_result(
                    results,
                    _mem_to_result(memory, score=vector_result.get("score", 0.5), source="vector", rank=rank),
                )
    except Exception as e:
        logger.warning("Vector search unavailable: {}", e)

    for rank, (memory, score) in enumerate(
        _token_search_memories(session, query, user_id=user_id, include_private=include_private, limit=limit * 3),
        start=1,
    ):
        if memory.id in results:
            results[memory.id].score = max(results[memory.id].score, score)
            _add_source(results[memory.id], "keyword", rank=rank)
        else:
            _merge_result(results, _mem_to_result(memory, score=score, source="keyword", rank=rank))

    for rank, (memory, score) in enumerate(
        _graph_memory_expansion(
            session,
            query,
            user_id=user_id,
            include_private=include_private,
            limit=config.MEMORY_HYBRID_GRAPH_RESULTS,
        ),
        start=1,
    ):
        _merge_result(results, _mem_to_result(memory, score=score, source="sql_graph", rank=rank))

    for rank, (source, score) in enumerate(
        _document_title_search(session, query, user_id=user_id, limit=limit), start=1
    ):
        key = f"source:{source.id}"
        if key not in results:
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
                evidence_text=source.summary or source.raw_text[:1200],
                retrieval_sources=["document_title"],
                source_ranks={"document_title": rank},
            )
        else:
            _add_source(results[key], "document_title", rank=rank)

    for rank, (entry, score) in enumerate(
        _raw_entry_search(session, query, user_id=user_id, include_private=include_private, limit=limit),
        start=1,
    ):
        key = f"raw:{entry.id}"
        if key not in results:
            results[key] = SearchResult(
                memory_id=key,
                text=entry.raw_text[:1200],
                memory_type="raw_entry",
                local_date=str(entry.local_date) if entry.local_date else "",
                confidence="observed_by_user",
                sensitivity=entry.sensitivity,
                source_entry_id=entry.id,
                score=score,
                source_kind=entry.source or "journal",
                evidence_text=entry.raw_text[:1200],
                retrieval_sources=["raw_keyword"],
                source_ranks={"raw_keyword": rank},
            )
        else:
            _add_source(results[key], "raw_keyword", rank=rank)

    for rank, hit in enumerate(graph_search_hits(session, query, user_id=user_id, limit=max(5, limit // 2)), start=1):
        key = f"graph:{hash(hit.text)}"
        if key not in results:
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
        else:
            _add_source(results[key], hit.source, rank=rank)

    _attach_user_importance(session, list(results.values()), user_id=user_id)
    sorted_results = rerank_results(
        list(results.values()),
        query=query,
        limit=limit,
        policy=ranking_policy,
    )
    if owned_session:
        session.close()
    return sorted_results
