"""Scoring, lexical, graph, and SQL helpers for hybrid memory search."""

from __future__ import annotations

import math
from collections import Counter

from sqlalchemy.orm import Session

from thoughtpins.config import config
from thoughtpins.db import DocumentSource, Entity, Memory, RawEntry, Relationship
from thoughtpins.memory.search_analysis import (
    _analyze_query,
    _phrase_score,
    _proximity_score,
    _token_score,
    _token_sequence,
    _tokens,
)
from thoughtpins.memory.search_types import QueryAnalysis, SearchResult


def _mem_to_result(memory: Memory, score: float = 0.5, source: str = "memory", rank: int | None = None) -> SearchResult:
    structured = memory.structured_json or {}
    return SearchResult(
        memory_id=memory.id,
        text=memory.text,
        memory_type=memory.memory_type,
        local_date=str(memory.local_date) if memory.local_date else "",
        confidence=memory.confidence,
        sensitivity=memory.sensitivity,
        source_entry_id=memory.raw_entry_id,
        score=score,
        source_kind=str(structured.get("source_kind") or "journal"),
        source_title=str(structured.get("title") or ""),
        evidence_text=str(structured.get("evidence_text") or memory.text),
        predicate=str(memory.predicate or ""),
        source_provenance=str(memory.source_provenance or ""),
        evidence_metadata=dict(structured),
        entity_names=[
            entity.canonical_name for entity in (memory.subject_entity, memory.object_entity) if entity is not None
        ],
        retrieval_sources=[source],
        source_ranks={source: rank} if rank is not None else {},
    )


def _memory_query(session: Session, *, user_id: str | None, include_private: bool):
    query = session.query(Memory).filter(Memory.valid_to.is_(None))
    if user_id:
        query = query.filter(Memory.user_id == user_id)
    if not include_private:
        query = query.join(RawEntry, Memory.raw_entry_id == RawEntry.id).filter(RawEntry.is_private == False)
    return query


def _merge_result(results: dict[str, SearchResult], result: SearchResult) -> None:
    existing = results.get(result.memory_id)
    if not existing:
        results[result.memory_id] = result
        return
    existing.score = max(existing.score, result.score)
    for source in result.retrieval_sources:
        _add_source(existing, source, rank=result.source_ranks.get(source))


def _add_source(result: SearchResult, source: str, rank: int | None = None) -> None:
    if source and source not in result.retrieval_sources:
        result.retrieval_sources.append(source)
    if source and rank is not None:
        old_rank = result.source_ranks.get(source)
        result.source_ranks[source] = rank if old_rank is None else min(old_rank, rank)


def _attach_user_importance(
    session: Session,
    results: list[SearchResult],
    *,
    user_id: str | None,
) -> None:
    entry_ids = {result.source_entry_id for result in results if result.source_entry_id}
    if not entry_ids:
        return
    query = session.query(
        RawEntry.id,
        RawEntry.user_importance,
        RawEntry.contextual_salience,
        RawEntry.salience_uncertainty,
    ).filter(RawEntry.id.in_(entry_ids))
    if user_id:
        query = query.filter(RawEntry.user_id == user_id)
    ratings = {
        entry_id: (rating, contextual_salience, salience_uncertainty)
        for entry_id, rating, contextual_salience, salience_uncertainty in query.all()
    }
    for result in results:
        rating, contextual_salience, salience_uncertainty = ratings.get(
            result.source_entry_id,
            (None, None, None),
        )
        result.user_importance = rating
        result.entry_salience = contextual_salience
        result.entry_salience_uncertainty = salience_uncertainty


def _raw_entry_query(session: Session, *, user_id: str | None, include_private: bool):
    query = session.query(RawEntry)
    if user_id:
        query = query.filter(RawEntry.user_id == user_id)
    if not include_private:
        query = query.filter(RawEntry.is_private == False)
    return query


def _token_search_memories(
    session: Session,
    query: str,
    *,
    user_id: str | None,
    include_private: bool,
    limit: int,
) -> list[tuple[Memory, float]]:
    analysis = _analyze_query(query)
    if not analysis.tokens:
        return []
    memories = _keyword_candidate_memories(
        session,
        analysis,
        user_id=user_id,
        include_private=include_private,
    )
    scored = _score_keyword_candidates(memories, analysis)
    return [(memory, score) for score, memory in sorted(scored, key=lambda item: item[0], reverse=True) if score > 0][
        :limit
    ]


def _keyword_candidate_memories(
    session: Session,
    analysis: QueryAnalysis,
    *,
    user_id: str | None,
    include_private: bool,
) -> list[Memory]:
    """Blend a recency window with globally targeted lexical candidates.

    A recency-only window is fast for everyday conversation but can hide an
    obscure fact in an older, large document collection. A few bounded SQL
    probes ensure distinctive query terms can nominate old memories before the
    BM25-lite scorer and MMR stage decide what is actually relevant.
    """
    candidate_limit = max(100, config.MEMORY_HYBRID_KEYWORD_CANDIDATES)
    base_query = _memory_query(session, user_id=user_id, include_private=include_private)
    recent = base_query.order_by(Memory.local_date.desc(), Memory.created_at_utc.desc()).limit(candidate_limit).all()
    candidates = {memory.id: memory for memory in recent}

    targeted_tokens = sorted(
        (token for token in analysis.tokens if len(token) >= 4),
        key=lambda token: (token not in analysis.high_value_tokens, -len(token), token),
    )[:6]
    per_token_limit = min(100, max(25, candidate_limit // 4))
    for token in targeted_tokens:
        matches = (
            _memory_query(session, user_id=user_id, include_private=include_private)
            .filter(Memory.text.ilike(f"%{token}%"))
            .order_by(Memory.local_date.desc(), Memory.created_at_utc.desc())
            .limit(per_token_limit)
            .all()
        )
        for memory in matches:
            candidates.setdefault(memory.id, memory)
    return list(candidates.values())


def _score_keyword_candidates(memories: list[Memory], analysis: QueryAnalysis) -> list[tuple[float, Memory]]:
    """Score candidates with BM25-lite ranking, rare-token guardrails, and phrase proximity."""
    if not memories or not analysis.tokens:
        return []
    haystacks = [
        (memory, search_text, _token_sequence(search_text), _tokens(search_text))
        for memory in memories
        for search_text in (_memory_search_text(memory),)
    ]
    document_frequency = {
        token: sum(1 for _, _, _, haystack in haystacks if token in haystack) for token in analysis.tokens
    }
    total_docs = len(haystacks)
    idf = {
        token: math.log(1 + ((total_docs - document_frequency[token] + 0.5) / (document_frequency[token] + 0.5)))
        for token in analysis.tokens
    }
    denominator = sum(max(0.001, value) for value in idf.values()) or 1.0
    rare_cutoff = max(3, int(total_docs * 0.03))
    avg_doc_len = sum(len(tokens) for _, _, tokens, _ in haystacks) / max(total_docs, 1)
    scored = [
        (
            _weighted_token_score(
                search_text,
                token_sequence,
                token_set,
                analysis,
                idf,
                denominator,
                document_frequency,
                rare_cutoff,
                avg_doc_len,
            ),
            memory,
        )
        for memory, search_text, token_sequence, token_set in haystacks
    ]
    return [(score, memory) for score, memory in scored if score > 0]


def _weighted_token_score(
    search_text: str,
    token_sequence: tuple[str, ...],
    haystack: set[str],
    analysis: QueryAnalysis,
    idf: dict[str, float],
    denominator: float,
    document_frequency: dict[str, int],
    rare_cutoff: int,
    avg_doc_len: float,
) -> float:
    overlap = analysis.tokens & haystack
    if not overlap:
        return 0.0
    coverage = sum(max(0.001, idf[token]) for token in overlap) / denominator
    bm25 = _bm25_score(token_sequence, analysis.tokens, idf, denominator, avg_doc_len)
    phrase = _phrase_score(search_text, analysis)
    proximity = _proximity_score(token_sequence, analysis.tokens)
    score = min(0.95, 0.36 + bm25 * 0.36 + coverage * 0.22 + phrase * 0.09 + proximity * 0.07)
    rare_hits = [token for token in overlap if document_frequency.get(token, 0) <= rare_cutoff]
    if rare_hits:
        max_idf = max(idf.values(), default=1.0) or 1.0
        rare_strength = sum(
            (idf[token] / max_idf) * (1.15 if token in analysis.high_value_tokens else 1.0) for token in rare_hits
        )
        rare_floor = 0.84 + min(0.12, rare_strength * 0.08) + min(0.02, len(rare_hits) * 0.006)
        score = max(score, min(0.98, rare_floor + phrase * 0.02))
    return score


def _bm25_score(
    token_sequence: tuple[str, ...],
    query_tokens: set[str],
    idf: dict[str, float],
    denominator: float,
    avg_doc_len: float,
) -> float:
    if not token_sequence or not query_tokens:
        return 0.0
    term_frequency = Counter(token_sequence)
    doc_len = max(1, len(token_sequence))
    avgdl = max(1.0, avg_doc_len)
    k1 = 1.2
    b = 0.72
    raw = 0.0
    for token in query_tokens:
        tf = term_frequency.get(token, 0)
        if tf <= 0:
            continue
        idf_value = max(0.001, idf.get(token, 0.001))
        normalizer = tf + k1 * (1 - b + b * (doc_len / avgdl))
        raw += idf_value * ((tf * (k1 + 1)) / normalizer)
    return min(1.0, raw / denominator)


def _memory_search_text(memory: Memory) -> str:
    structured = memory.structured_json or {}
    return " ".join(
        str(part or "")
        for part in (
            memory.text,
            memory.memory_type,
            memory.predicate,
            memory.source_provenance,
            structured.get("title"),
            structured.get("source_kind"),
            structured.get("evidence_text"),
        )
    )


def _raw_entry_search(
    session: Session,
    query: str,
    *,
    user_id: str | None,
    include_private: bool,
    limit: int,
) -> list[tuple[RawEntry, float]]:
    query_tokens = _tokens(query)
    if not query_tokens:
        return []
    entries = (
        _raw_entry_query(session, user_id=user_id, include_private=include_private)
        .order_by(RawEntry.local_date.desc(), RawEntry.created_at_utc.desc())
        .limit(1000)
        .all()
    )
    scored = [
        (_token_score(entry.raw_text, query_tokens), entry)
        for entry in entries
        if not _raw_entry_fully_superseded(entry)
    ]
    return [(entry, score) for score, entry in sorted(scored, key=lambda item: item[0], reverse=True) if score > 0.55][
        :limit
    ]


def _raw_entry_fully_superseded(entry: RawEntry) -> bool:
    memories = list(entry.memories or [])
    return bool(memories) and all(memory.valid_to is not None for memory in memories)


def _document_title_search(
    session: Session,
    query: str,
    *,
    user_id: str | None,
    limit: int,
) -> list[tuple[DocumentSource, float]]:
    query_tokens = _tokens(query)
    if not query_tokens:
        return []
    q = session.query(DocumentSource)
    if user_id:
        q = q.filter(DocumentSource.user_id == user_id)
    sources = q.order_by(DocumentSource.created_at_utc.desc()).limit(1000).all()
    scored: list[tuple[float, DocumentSource]] = []
    for source in sources:
        reading_analysis = (source.metadata_json or {}).get("reading_analysis", {})
        analysis_terms: list[str] = []
        if isinstance(reading_analysis, dict):
            for key in ("publisher", "topics", "key_concepts"):
                value = reading_analysis.get(key)
                if isinstance(value, list):
                    analysis_terms.extend(str(item) for item in value)
                elif value:
                    analysis_terms.append(str(value))
        text = " ".join(
            str(part or "")
            for part in (
                source.title,
                source.author,
                source.source_domain,
                source.summary,
                source.source_url,
                " ".join(analysis_terms),
            )
        )
        score = _token_score(text, query_tokens)
        if score > 0:
            scored.append((min(0.88, score + 0.05), source))
    return [(source, score) for score, source in sorted(scored, key=lambda item: item[0], reverse=True)[:limit]]


def _graph_memory_expansion(
    session: Session,
    query: str,
    *,
    user_id: str | None,
    include_private: bool,
    limit: int,
) -> list[tuple[Memory, float]]:
    query_tokens = _tokens(query)
    if not query_tokens:
        return []
    entity_ids = _matched_entity_ids(session, query_tokens, user_id=user_id)
    if not entity_ids:
        return []
    related_ids = set(entity_ids)
    frontier = set(entity_ids)
    for _ in range(max(0, config.MEMORY_HYBRID_GRAPH_HOPS)):
        rel_q = session.query(Relationship).filter(
            (Relationship.source_entity_id.in_(frontier)) | (Relationship.target_entity_id.in_(frontier))
        )
        if user_id:
            rel_q = rel_q.filter(Relationship.user_id == user_id)
        next_frontier: set[str] = set()
        for rel in rel_q.limit(500).all():
            next_frontier.add(rel.source_entity_id)
            next_frontier.add(rel.target_entity_id)
        next_frontier -= related_ids
        related_ids |= next_frontier
        frontier = next_frontier
        if not frontier:
            break

    memory_q = _memory_query(session, user_id=user_id, include_private=include_private).filter(
        (Memory.subject_entity_id.in_(related_ids)) | (Memory.object_entity_id.in_(related_ids))
    )
    memories = memory_q.order_by(Memory.local_date.desc(), Memory.created_at_utc.desc()).limit(limit).all()
    return [
        (memory, 0.78 if memory.subject_entity_id in entity_ids or memory.object_entity_id in entity_ids else 0.68)
        for memory in memories
    ]


def _matched_entity_ids(session: Session, query_tokens: set[str], *, user_id: str | None) -> list[str]:
    q = session.query(Entity)
    if user_id:
        q = q.filter(Entity.user_id == user_id)
    matches: list[str] = []
    for entity in q.limit(5000).all():
        aliases = entity.aliases_json or []
        text = " ".join([entity.canonical_name, entity.type, *[str(alias) for alias in aliases]])
        if _token_score(text, query_tokens) > 0:
            matches.append(entity.id)
    return matches


def graph_search_hits(session: Session, query: str, *, user_id: str | None, limit: int = 10):
    from thoughtpins.memory.graph_backend import GraphSearchHit

    query_tokens = _tokens(query)
    if not query_tokens:
        return []
    entity_ids = _matched_entity_ids(session, query_tokens, user_id=user_id)
    if not entity_ids:
        return []
    rel_q = session.query(Relationship).filter(
        (Relationship.source_entity_id.in_(entity_ids)) | (Relationship.target_entity_id.in_(entity_ids))
    )
    if user_id:
        rel_q = rel_q.filter(Relationship.user_id == user_id)
    hits: list[GraphSearchHit] = []
    for rel in rel_q.order_by(Relationship.last_seen_at.desc()).limit(limit * 2).all():
        source = rel.source_entity.canonical_name if rel.source_entity else rel.source_entity_id
        target = rel.target_entity.canonical_name if rel.target_entity else rel.target_entity_id
        text = f"{source} -[{rel.relation_type}]-> {target}"
        if rel.notes:
            text += f". {rel.notes[:240]}"
        hits.append(
            GraphSearchHit(
                text=text,
                score=0.74,
                source="internal_sql_graph",
                entity_names=[str(source), str(target)],
                metadata={"relationship_id": rel.id, "raw_entry_id": rel.raw_entry_id},
            )
        )
    return hits[:limit]
