from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace


def test_keyword_candidates_recall_rare_fact_outside_recency_window(isolated_db, monkeypatch) -> None:
    from thoughtpins.config import config
    from thoughtpins.db import Memory, RawEntry, User
    from thoughtpins.memory.search_support import _analyze_query, _keyword_candidate_memories
    from thoughtpins.store import get_session
    from thoughtpins.utils import hash_text

    monkeypatch.setattr(config, "MEMORY_HYBRID_KEYWORD_CANDIDATES", 5)
    session = get_session()
    try:
        user = User(display_name="Recall test", api_key="recall-test")
        session.add(user)
        session.flush()

        old_entry = RawEntry(
            user_id=user.id,
            raw_text="The orchidcipher was written on the blue receipt.",
            content_hash=hash_text("rare-old-entry"),
            local_date=date.today() - timedelta(days=3650),
            processed_status="completed",
        )
        session.add(old_entry)
        session.flush()
        rare_memory = Memory(
            user_id=user.id,
            raw_entry_id=old_entry.id,
            memory_type="detail",
            text="The orchidcipher was written on the blue receipt.",
            local_date=old_entry.local_date,
        )
        session.add(rare_memory)

        for index in range(110):
            text = f"Recent ordinary note number {index}"
            entry = RawEntry(
                user_id=user.id,
                raw_text=text,
                content_hash=hash_text(text),
                local_date=date.today(),
                processed_status="completed",
            )
            session.add(entry)
            session.flush()
            session.add(
                Memory(
                    user_id=user.id,
                    raw_entry_id=entry.id,
                    memory_type="detail",
                    text=text,
                    local_date=entry.local_date,
                )
            )
        session.commit()

        candidates = _keyword_candidate_memories(
            session,
            _analyze_query("orchidcipher"),
            user_id=user.id,
            include_private=True,
        )
        assert rare_memory.id in {candidate.id for candidate in candidates}
    finally:
        session.close()


def test_reranker_preserves_a_missing_rare_query_aspect() -> None:
    from thoughtpins.memory.ranking import rerank_results
    from thoughtpins.memory.search_types import SearchResult

    def result(memory_id: str, text: str, score: float) -> SearchResult:
        return SearchResult(
            memory_id=memory_id,
            text=text,
            memory_type="source_excerpt",
            local_date="2026-07-13",
            confidence="observed_by_user",
            sensitivity="personal",
            source_entry_id=memory_id,
            score=score,
            evidence_text=text,
            retrieval_sources=["keyword"],
            source_ranks={"keyword": int((1.0 - score) * 100) + 1},
        )

    candidates = [
        result("a", "the scarlet thread of murder runs through the case", 0.98),
        result("b", "scarlet evidence connected the suspect to London", 0.94),
        result("c", "the murder investigation used a chemical test", 0.93),
        result("d", "the thread connected several witnesses", 0.92),
        result("e", "the detective reconstructed the murder timeline", 0.91),
        result("f", "RACHE was the obscure word written at the scene", 0.55),
    ]

    ranked = rerank_results(candidates, query="RACHE scarlet thread murder", limit=4)

    assert any("rache" in candidate.text.lower() for candidate in ranked)
    assert ranked[0].memory_id == "a"


def test_keyword_rarity_distinguishes_unique_anchor_from_common_uncommon_terms() -> None:
    from thoughtpins.memory.search_support import _analyze_query, _score_keyword_candidates

    def memory(memory_id: str, text: str):
        return SimpleNamespace(
            id=memory_id,
            text=text,
            memory_type="source_excerpt",
            predicate="",
            source_provenance="",
            structured_json={},
        )

    candidates = [memory(f"scarlet-{index}", f"A scarlet observation from chapter {index}.") for index in range(80)]
    candidates.extend(
        [
            memory("thread", "The thread connected the witnesses."),
            memory("murder", "The murder remained unexplained."),
            memory("rache", "RACHE was the obscure word written at the scene."),
        ]
    )

    scored = _score_keyword_candidates(
        candidates,
        _analyze_query("RACHE scarlet thread murder"),
    )
    scores = {candidate.id: score for score, candidate in scored}

    assert scores["rache"] > scores["scarlet-0"]
