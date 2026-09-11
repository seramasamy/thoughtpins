from __future__ import annotations

from datetime import date

from thoughtpins.memory.ranking import rerank_results
from thoughtpins.memory.search_types import SearchResult
from thoughtpins.memory.temporal_relevance import parse_temporal_window, temporal_window_match


def test_relative_date_windows_are_calendar_aware() -> None:
    as_of = date(2026, 7, 21)

    for query, expected in [
        ("what happened 5 days ago?", date(2026, 7, 16)),
        ("what happened last Saturday?", date(2026, 7, 18)),
        ("what happened last week?", date(2026, 7, 13)),
    ]:
        window = parse_temporal_window(query, as_of=as_of)
        assert window is not None
        assert window.start == expected
    month = parse_temporal_window("what happened last month?", as_of=as_of)
    assert month is not None
    assert month.end == date(2026, 6, 30)


def test_temporal_match_decays_outside_the_requested_window() -> None:
    window = parse_temporal_window("what happened yesterday?", as_of=date(2026, 7, 21))

    assert temporal_window_match("2026-07-20", window) == 1.0
    assert temporal_window_match("2026-07-19", window) > temporal_window_match("2026-07-10", window)


def test_explicit_relative_date_breaks_a_close_lexical_tie() -> None:
    target = _result("target", "2026-07-16", 0.69)
    decoy = _result("decoy", "2026-06-16", 0.70)

    ranked = rerank_results(
        [decoy, target],
        query="What happened at the charity event 5 days ago?",
        limit=2,
        as_of_date=date(2026, 7, 21),
    )

    assert ranked[0].memory_id == "target"
    assert ranked[0].ranking_signals["temporal_query_match"] == 1.0


def _result(memory_id: str, local_date: str, score: float) -> SearchResult:
    return SearchResult(
        memory_id=memory_id,
        text="The charity event happened.",
        memory_type="event",
        local_date=local_date,
        confidence="user_reported",
        sensitivity="personal",
        source_entry_id=memory_id,
        score=score,
        evidence_text="The charity event happened.",
        retrieval_sources=["keyword"],
        source_ranks={"keyword": 1},
    )
