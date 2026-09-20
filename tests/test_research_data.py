from dataclasses import asdict

import pytest

from thoughtpins.memory.research_data import evermem_judgment, evermem_query, evermem_sources, message_indices


def corpus():
    return [
        {
            "topic_id": "01",
            "date": "2026-01-02",
            "dialogues": {
                "Group 1": [
                    {"speaker": "A", "time": "12:00", "dialogue": "I moved to Rome.", "message_index": 10},
                    {"speaker": "B", "time": "12:01", "dialogue": "Noted.", "message_index": 14},
                ],
                "Group 2": None,
                "Group 3": [],
            },
        }
    ]


def judgment():
    return {
        "topic_id": "01",
        "id": "q",
        "Q": "Where did A move?",
        "A": "Rome",
        "R": [{"date": "2026-01-02", "group": "Group 1", "message_index": "10,14"}],
    }


def test_nonordinal_message_references_map_to_exact_dated_source() -> None:
    sources = evermem_sources(corpus(), topic="01")
    assert evermem_judgment(judgment(), sources) == {
        "01/2026-01-02/group1": ("01/2026-01-02/group1/10", "01/2026-01-02/group1/14")
    }
    assert asdict(evermem_query(judgment())) == {
        "query_id": "01/q",
        "text": "Where did A move?",
        "group": "01",
        "as_of": "",
    }
    assert "Rome" not in str(asdict(evermem_query(judgment())))


def test_closed_ranges_and_duplicate_references() -> None:
    assert message_indices("1,4-6, 8,10-11,4") == (1, 4, 5, 6, 8, 10, 11)


@pytest.mark.parametrize("value", ["4-2", "one", "1;2", "", None, True, "1-999999"])
def test_ambiguous_message_references_fail(value) -> None:
    with pytest.raises(ValueError):
        message_indices(value)


def test_missing_message_is_not_reinterpreted_as_ordinal_position() -> None:
    q = judgment()
    q["R"][0]["message_index"] = "1"
    with pytest.raises(ValueError, match="message absent"):
        evermem_judgment(q, evermem_sources(corpus(), topic="01"))


def test_event_identity_survives_identical_text_on_another_date() -> None:
    rows = corpus() + corpus()
    rows[1]["date"] = "2026-01-03"
    sources = evermem_sources(rows, topic="01")
    assert sources[0].text == sources[1].text
    assert sources[0].source_id != sources[1].source_id
    assert set(sources[0].message_ids).isdisjoint(sources[1].message_ids)


def test_duplicate_ids_and_cross_topic_are_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate dated"):
        evermem_sources(corpus() + corpus(), topic="01")
    with pytest.raises(ValueError, match="Cross-topic"):
        evermem_sources(corpus(), topic="02")


def test_all_observable_options_are_preserved_without_gold_choice() -> None:
    row = judgment()
    row["options"] = {"A": "Rome", "B": "Oslo", "C": "Lima", "D": "Kyoto"}
    row["A"] = "hidden gold choice marker"
    query = evermem_query(row)
    assert all(value in query.text for value in row["options"].values())
    assert row["A"] not in query.text
