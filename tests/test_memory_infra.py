from __future__ import annotations


def test_hybrid_search_uses_sql_graph_and_documents(isolated_db, monkeypatch):
    from thoughtpins.config import config
    from thoughtpins.memory import search as memory_search
    from thoughtpins.memory.eval import seed_memory_infra_fixture
    from thoughtpins.store import get_session

    class FakeVectorStore:
        def search(self, query: str, limit: int = 10, *, user_id: str | None = None):
            return []

    monkeypatch.setattr(memory_search, "get_vector_store", lambda: FakeVectorStore())
    monkeypatch.setattr(config, "MEMORY_CONTEXT_FULL_INLINE_MAX_CHARS", 10)
    monkeypatch.setattr(type(config), "MEMORY_CONTEXT_FULL_INLINE_MAX_CHARS", 10)

    session = get_session()
    try:
        user_id = seed_memory_infra_fixture(session)
        project_results = memory_search.search(
            "what technology does Project Atlas use?",
            session=session,
            user_id=user_id,
            limit=10,
        )
        assert any("PostgreSQL" in result.evidence_text or "PostgreSQL" in result.text for result in project_results)
        assert any("sql_graph" in result.retrieval_sources for result in project_results)

        doc_results = memory_search.search("violet keystone", session=session, user_id=user_id, limit=10)
        assert any(result.source_kind == "document" for result in doc_results)
        assert any("violet keystone" in result.evidence_text for result in doc_results)
    finally:
        session.close()


def test_memory_audit_and_eval_grade_clean_fixture(isolated_db, monkeypatch):
    from thoughtpins.memory import search as memory_search
    from thoughtpins.memory.audit import audit_memory_system
    from thoughtpins.memory.eval import run_memory_infra_eval, seed_memory_infra_fixture
    from thoughtpins.store import get_session

    class FakeVectorStore:
        def search(self, query: str, limit: int = 10, *, user_id: str | None = None):
            return []

    monkeypatch.setattr(memory_search, "get_vector_store", lambda: FakeVectorStore())

    session = get_session()
    try:
        user_id = seed_memory_infra_fixture(session)
        audit = audit_memory_system(session, user_id=user_id)
        assert audit.score >= 90
        assert audit.graph["provider"] == "internal_sql"

        result = run_memory_infra_eval(session, user_id=user_id)
        assert result.score >= 90
        assert all(case.passed for case in result.cases), result.as_dict()
        assert result.retrieval_metrics is not None
        assert result.retrieval_metrics.mean_recall_at_k == 1.0
        assert result.retrieval_metrics.mean_ndcg_at_k >= 0.95
        assert result.retrieval_metrics.worst_case_ndcg_at_k == 1.0
        assert {ablation.policy for ablation in result.ranking_ablations} == {
            "social-episodic-v2",
            "without-lexical-evidence",
            "without-rank-fusion",
            "without-structural-priors",
            "without-salience-priors",
            "without-social-evidence",
            "without-diversity",
        }
    finally:
        session.close()


def test_graph_backend_health_is_local_first(isolated_db):
    from thoughtpins.memory.graph_backend import graph_backend_health
    from thoughtpins.store import get_session

    session = get_session()
    try:
        health = graph_backend_health(session)
        assert health["provider"] == "internal_sql"
        assert health["status"] == "ok"
        assert "ontology" in health
    finally:
        session.close()


def test_keyword_search_ranks_rare_exact_terms_above_generic_overlap(isolated_db, monkeypatch):
    from datetime import datetime, timezone

    from thoughtpins.db import Memory, RawEntry, User
    from thoughtpins.memory import search as memory_search
    from thoughtpins.store import get_session
    from thoughtpins.utils import hash_text

    class FakeVectorStore:
        def search(self, query: str, limit: int = 10, *, user_id: str | None = None):
            return []

    monkeypatch.setattr(memory_search, "get_vector_store", lambda: FakeVectorStore())

    session = get_session()
    try:
        user = User(email="rare-token@example.com")
        session.add(user)
        session.flush()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        raw = RawEntry(
            user_id=user.id,
            created_at_utc=now,
            local_date=now.date(),
            local_time="12:00",
            source="test",
            raw_text="Rare-token search fixture.",
            content_hash=hash_text("rare-token search fixture"),
            is_private=False,
            sensitivity="personal",
            processed_status="processed",
        )
        session.add(raw)
        session.flush()
        generic_text = (
            "From source 'A Study in Scarlet' chunk: this scarlet thread of murder "
            "runs through the chapter but omits the rare clue."
        )
        for index in range(6):
            session.add(
                Memory(
                    user_id=user.id,
                    raw_entry_id=raw.id,
                    memory_type="source_excerpt",
                    text=f"{generic_text} Generic decoy {index}.",
                    local_date=now.date(),
                    sensitivity="personal",
                    confidence="observed_by_user",
                    structured_json={"source_kind": "document", "evidence_text": generic_text},
                )
            )
        session.add(
            Memory(
                user_id=user.id,
                raw_entry_id=raw.id,
                memory_type="source_excerpt",
                text="From source 'A Study in Scarlet' chunk: the word RACHE was written on the wall.",
                local_date=now.date(),
                sensitivity="personal",
                confidence="observed_by_user",
                structured_json={
                    "source_kind": "document",
                    "evidence_text": "The word RACHE was written on the wall.",
                },
            )
        )
        session.commit()

        results = memory_search.search(
            "RACHE scarlet thread of murder",
            session=session,
            user_id=user.id,
            include_private=True,
            limit=3,
        )
        assert any("RACHE" in result.evidence_text or "RACHE" in result.text for result in results)
    finally:
        session.close()


def test_rank_fusion_records_signals_and_diversifies_context(isolated_db, monkeypatch):
    from datetime import datetime, timezone

    from thoughtpins.db import Entity, Memory, RawEntry, Relationship, User
    from thoughtpins.memory import search as memory_search
    from thoughtpins.store import get_session
    from thoughtpins.utils import hash_text

    class FakeVectorStore:
        def __init__(self, first_id: str):
            self.first_id = first_id

        def search(self, query: str, limit: int = 10, *, user_id: str | None = None):
            return [{"id": self.first_id, "score": 0.41}]

    session = get_session()
    try:
        user = User(email="fusion@example.com")
        session.add(user)
        session.flush()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        raw = RawEntry(
            user_id=user.id,
            created_at_utc=now,
            local_date=now.date(),
            local_time="12:00",
            source="test",
            raw_text="Fusion test fixture.",
            content_hash=hash_text("fusion test fixture"),
            is_private=False,
            sensitivity="personal",
            processed_status="processed",
        )
        session.add(raw)
        session.flush()
        atlas = Entity(user_id=user.id, canonical_name="Project Atlas", type="project")
        postgres = Entity(user_id=user.id, canonical_name="PostgreSQL", type="technology")
        session.add_all([atlas, postgres])
        session.flush()

        primary = Memory(
            user_id=user.id,
            raw_entry_id=raw.id,
            memory_type="observation",
            subject_entity_id=atlas.id,
            object_entity_id=postgres.id,
            text="Project Atlas uses PostgreSQL for the audit trail.",
            local_date=now.date(),
            sensitivity="personal",
            confidence="observed_by_user",
        )
        session.add(primary)
        for index in range(4):
            session.add(
                Memory(
                    user_id=user.id,
                    raw_entry_id=raw.id,
                    memory_type="observation",
                    text=f"Project Atlas audit trail duplicate note {index}: PostgreSQL audit trail.",
                    local_date=now.date(),
                    sensitivity="personal",
                    confidence="observed_by_user",
                )
            )
        second_topic = Memory(
            user_id=user.id,
            raw_entry_id=raw.id,
            memory_type="observation",
            text="Project Atlas also had a backup restore drill with Priya.",
            local_date=now.date(),
            sensitivity="personal",
            confidence="observed_by_user",
        )
        session.add(second_topic)
        session.add(
            Relationship(
                user_id=user.id,
                source_entity_id=atlas.id,
                target_entity_id=postgres.id,
                relation_type="uses_technology",
                raw_entry_id=raw.id,
            )
        )
        session.commit()

        monkeypatch.setattr(memory_search, "get_vector_store", lambda: FakeVectorStore(primary.id))
        results = memory_search.search(
            "Project Atlas PostgreSQL audit restore", session=session, user_id=user.id, limit=3
        )

        fused = next(result for result in results if result.memory_id == primary.id)
        assert {"vector", "keyword", "sql_graph"} & set(fused.retrieval_sources)
        assert fused.ranking_signals["rrf"] > 0
        assert any("backup restore" in result.text for result in results)
    finally:
        session.close()


def test_phrase_and_proximity_ranking_beats_noisy_bag_of_words(isolated_db, monkeypatch):
    from datetime import datetime, timezone

    from thoughtpins.db import Memory, RawEntry, User
    from thoughtpins.memory import search as memory_search
    from thoughtpins.store import get_session
    from thoughtpins.utils import hash_text

    class FakeVectorStore:
        def search(self, query: str, limit: int = 10, *, user_id: str | None = None):
            return []

    monkeypatch.setattr(memory_search, "get_vector_store", lambda: FakeVectorStore())

    session = get_session()
    try:
        user = User(email="phrase-proximity@example.com")
        session.add(user)
        session.flush()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        raw = RawEntry(
            user_id=user.id,
            created_at_utc=now,
            local_date=now.date(),
            local_time="19:30",
            source="test",
            raw_text="Phrase and proximity fixture.",
            content_hash=hash_text("phrase and proximity fixture"),
            is_private=False,
            sensitivity="personal",
            processed_status="processed",
        )
        session.add(raw)
        session.flush()
        exact = Memory(
            user_id=user.id,
            raw_entry_id=raw.id,
            memory_type="observation",
            text=(
                "At Nomad Cafe, Maya recommended the saffron pistachio gelato "
                "after we talked through the Lumia notebook idea."
            ),
            local_date=now.date(),
            sensitivity="personal",
            confidence="observed_by_user",
        )
        decoy = Memory(
            user_id=user.id,
            raw_entry_id=raw.id,
            memory_type="observation",
            text=(
                "Maya liked the cafe playlist. The notebook was still in my bag. "
                "Later I saw saffron tea, a pistachio pastry, and a gelato sign at another place."
            ),
            local_date=now.date(),
            sensitivity="personal",
            confidence="observed_by_user",
        )
        session.add_all([decoy, exact])
        session.commit()

        results = memory_search.search(
            '"saffron pistachio gelato" Maya Nomad Cafe',
            session=session,
            user_id=user.id,
            include_private=True,
            limit=2,
        )

        assert results[0].memory_id == exact.id
        assert results[0].ranking_signals["phrase"] > results[1].ranking_signals["phrase"]
        assert results[0].ranking_signals["proximity"] >= results[1].ranking_signals["proximity"]
        for result in results:
            assert 0 <= result.score <= 1
            assert {"base", "lexical", "phrase", "proximity", "rrf", "specificity", "final"} <= set(
                result.ranking_signals
            )
            assert all(0 <= value <= 1 for value in result.ranking_signals.values())
    finally:
        session.close()


def test_keyword_scoring_is_bounded_for_sparse_and_repetitive_queries(isolated_db, monkeypatch):
    from datetime import datetime, timezone

    from thoughtpins.db import Memory, RawEntry, User
    from thoughtpins.memory import search as memory_search
    from thoughtpins.store import get_session
    from thoughtpins.utils import hash_text

    class FakeVectorStore:
        def search(self, query: str, limit: int = 10, *, user_id: str | None = None):
            return []

    monkeypatch.setattr(memory_search, "get_vector_store", lambda: FakeVectorStore())

    session = get_session()
    try:
        user = User(email="bounded-ranking@example.com")
        session.add(user)
        session.flush()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        raw = RawEntry(
            user_id=user.id,
            created_at_utc=now,
            local_date=now.date(),
            local_time="08:15",
            source="test",
            raw_text="Bounded ranking fixture.",
            content_hash=hash_text("bounded ranking fixture"),
            is_private=False,
            sensitivity="personal",
            processed_status="processed",
        )
        session.add(raw)
        session.flush()
        session.add(
            Memory(
                user_id=user.id,
                raw_entry_id=raw.id,
                memory_type="idea",
                text="Recipe note: repeat repeat repeat basil tomato sourdough with a tiny vinegar adjustment.",
                local_date=now.date(),
                sensitivity="personal",
                confidence="observed_by_user",
            )
        )
        session.commit()

        sparse_results = memory_search.search("??", session=session, user_id=user.id, include_private=True, limit=3)
        assert sparse_results == []

        repeated_results = memory_search.search(
            "repeat repeat repeat basil tomato",
            session=session,
            user_id=user.id,
            include_private=True,
            limit=3,
        )
        assert repeated_results
        for result in repeated_results:
            assert 0 <= result.score <= 1
            assert all(0 <= value <= 1 for value in result.ranking_signals.values())
    finally:
        session.close()
