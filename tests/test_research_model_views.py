from thoughtpins.memory.research_data import ResearchSource
from thoughtpins.memory.research_model_views import evidence_view, response_ranking


def test_matched_context_and_permutation_preserve_original_fallback() -> None:
    sources = {sid: ResearchSource(sid, sid * 1000, "2026-01-01") for sid in ("a", "b")}
    view = evidence_view("q", "A question", sources, ["b", "a"], byte_budget=400)
    assert view["evidence_bytes"] <= 400
    assert set(view["truncated_sources"]) == {"a", "b"}
    assert response_ranking(
        {"kind": "chat", "status": "timeout"}, candidate_ids=view["candidate_ids"], baseline_ids=view["baseline_ids"]
    ) == (["b", "a"], "timeout")


def test_specialized_rerank_requires_every_id_and_finite_score() -> None:
    valid = {
        "kind": "rerank",
        "status": "ok",
        "data": [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.1}],
    }
    assert response_ranking(valid, candidate_ids=["b", "a"], baseline_ids=["a", "b"]) == (["a", "b"], None)
    bad = {**valid, "data": [{"index": 1, "relevance_score": float("nan")}]}
    assert response_ranking(bad, candidate_ids=["b", "a"], baseline_ids=["b", "a"])[0] == ["b", "a"]
