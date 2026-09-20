"""Reusable offline experiment engine. No database, credentials or gold labels."""

from __future__ import annotations

import time
from datetime import date

import numpy as np

from thoughtpins.memory.ranking import clone_candidates_for_rerank, rerank_results
from thoughtpins.memory.research_data import ResearchQuery, ResearchSource
from thoughtpins.memory.research_features import query_facets, query_features
from thoughtpins.memory.research_learning import apply_ranker
from thoughtpins.memory.research_retrieval import LexicalIndex, fuse_rankings, stable_order
from thoughtpins.memory.research_selection import greedy_coverage
from thoughtpins.memory.search_types import SearchResult


class ResearchIndex:
    def __init__(
        self, sources: list[ResearchSource], vectors: np.ndarray | None, *, source_kind: str = "journal"
    ) -> None:
        started = time.perf_counter()
        self.sources = sources
        self.source_kind = source_kind
        self.ids = [s.source_id for s in sources]
        if len(set(self.ids)) != len(self.ids) or (
            vectors is not None and (vectors.ndim != 2 or len(vectors) != len(sources))
        ):
            raise ValueError("Unique sources and dense rows must align")
        self.vectors = vectors
        if vectors is not None and (not np.isfinite(vectors).all() or np.any(np.linalg.norm(vectors, axis=1) == 0)):
            raise ValueError("Dense vectors must be finite and nonzero")
        self.lexical = LexicalIndex([s.text for s in sources])
        self.build_seconds = time.perf_counter() - started

    def rank(
        self,
        query: ResearchQuery,
        query_vector: np.ndarray | None,
        *,
        k1: float,
        b: float,
        candidate_limit: int = 50,
        fitted: dict | None = None,
        coverage: dict | None = None,
        include_current: bool = True,
    ) -> dict:
        started = time.perf_counter()
        if query_vector is not None and (
            query_vector.ndim != 1 or not np.isfinite(query_vector).all() or np.linalg.norm(query_vector) == 0
        ):
            raise ValueError("Query vector must be finite, one-dimensional and nonzero")
        historical = self.lexical.scores(query.text)
        sparse = self.lexical.scores(query.text, k1=k1, b=b)
        dense_available = self.vectors is not None and query_vector is not None
        cosine = (
            self.vectors @ query_vector
            if self.vectors is not None and query_vector is not None
            else np.zeros(len(self.ids))
        )
        sparse_order = stable_order(sparse)
        dense_order = stable_order(cosine, self.ids) if dense_available else []
        historical_order = stable_order(historical)
        sparse_ids = [self.ids[i] for i in sparse_order]
        dense_ids = [self.ids[i] for i in dense_order]
        hybrid = fuse_rankings({"sparse": sparse_ids[:candidate_limit], "dense": dense_ids[:candidate_limit]})
        pool = [sid for sid, _ in hybrid[:candidate_limit]]
        arms = {
            "B0": [self.ids[i] for i in historical_order[:candidate_limit]],
            "B1": sparse_ids[:candidate_limit],
            "B3": dense_ids[:candidate_limit],
            "B4": pool,
        }
        retrieval_seconds = time.perf_counter() - started
        if include_current:
            arms["B2"] = self._current_policy(query, historical, historical_order)
        if fitted is not None:
            positions = {sid: i for i, sid in enumerate(self.ids)}
            sr, dr = {sid: i for i, sid in enumerate(sparse_ids, 1)}, {sid: i for i, sid in enumerate(dense_ids, 1)}
            sources = [self.sources[positions[sid]] for sid in pool]
            features = query_features(
                query.text,
                sources,
                sparse=[float(sparse[positions[sid]]) for sid in pool],
                dense=[float(cosine[positions[sid]]) for sid in pool],
                sparse_ranks=[sr[sid] if sr[sid] <= candidate_limit else 0 for sid in pool],
                dense_ranks=[dr[sid] if sid in dr and dr[sid] <= candidate_limit else 0 for sid in pool],
            )
            features[:, fitted.get("removed_features", [])] = 0
            scores = apply_ranker(features, fitted)
            arms["learned"] = [pool[i] for i in stable_order(scores, pool)]
            if coverage is not None:
                relevance = np.clip(scores / max(float(scores.max()), 1e-9), 0, 1)
                support, weights = query_facets(query.text, sources, relevance, gate=coverage["gate"])
                order = greedy_coverage(pool, support, relevance, weights, eta=coverage["eta"], limit=10)
                arms["coverage"] = [pool[i] for i in order]
        return {
            "arms": arms,
            "retrieval_seconds": retrieval_seconds,
            "total_local_seconds": time.perf_counter() - started,
            "index_build_seconds": self.build_seconds,
            "candidate_limit": candidate_limit,
            "corpus_sources": len(self.sources),
            "dense_available": dense_available,
        }

    def _current_policy(self, query: ResearchQuery, historical: np.ndarray, historical_order: list[int]) -> list[str]:
        candidates = [
            SearchResult(
                memory_id=s.source_id,
                source_entry_id=s.source_id,
                text=s.text,
                evidence_text=s.text,
                local_date=s.date,
                memory_type="document" if self.source_kind == "document" else "conversation_session",
                source_kind=self.source_kind,
                source_title=s.text.split("\n", 1)[0] if self.source_kind == "document" else "",
                confidence="quoted_source" if self.source_kind == "document" else "user_reported",
                sensitivity="personal",
                score=float(historical[i]),
                evidence_metadata={"session_date": s.date},
                retrieval_sources=["benchmark_bm25"],
                source_ranks={"benchmark_bm25": rank},
            )
            for rank, i in enumerate(historical_order, 1)
            for s in [self.sources[i]]
        ]
        results = rerank_results(
            clone_candidates_for_rerank(candidates),
            query=query.text,
            limit=10,
            as_of_date=date.fromisoformat(query.as_of) if query.as_of else date(2026, 9, 19),
        )
        return [c.source_entry_id for c in results]
