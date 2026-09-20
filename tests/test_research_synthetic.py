from thoughtpins.memory.research_synthetic import CATEGORIES, synthetic_cases


def test_labels_are_fixed_by_state_and_events_not_rendered_answer_matching() -> None:
    cases = synthetic_cases(seed=7)
    assert len(cases) == 200
    assert set(c["category"] for c in cases) == set(CATEGORIES)
    for case in cases:
        source_ids = set(case["query"]["source_ids"])
        assert set(case["judgment"]["relevant"]).issubset(source_ids)
        assert len(source_ids) == 12
        assert all(not any(marker in sid for marker in ("distractor", "old", "new", "other")) for sid in source_ids)
        assert "relevant" not in case["query"]
    multi = next(c for c in cases if c["category"] == "multiple_sources")
    assert len(multi["judgment"]["relevant"]) == 2
    assert [e["event_day"] for e in multi["state"][:2]] == ["2024-02-01", "2025-02-01"]


def test_final_role_has_disjoint_identities_and_templates() -> None:
    dev = synthetic_cases(seed=9, count=1)[0]
    final = synthetic_cases(seed=10, count=1, role="final")[0]
    assert set(dev["query"]["source_ids"]).isdisjoint(final["query"]["source_ids"])
    assert dev["query"]["text"] != final["query"]["text"]
