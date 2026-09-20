"""Pure public-data projections for offline retrieval studies.

Source/query objects deliberately have no answer, relevance or benchmark-type
fields. Judgment parsing is a separate evaluator-only function.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class ResearchSource:
    source_id: str
    text: str
    date: str = ""
    speaker: str = ""
    message_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResearchQuery:
    query_id: str
    text: str
    group: str
    as_of: str = ""


def _day(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid reference date type")
    return date.fromisoformat(value).isoformat()


def _group(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"group\s*[1-3]", value.strip(), re.IGNORECASE):
        raise ValueError("Unrecognized group")
    return "group" + value.strip()[-1]


def message_indices(value: Any) -> tuple[int, ...]:
    """Parse explicit message IDs, never list positions, including closed ranges."""
    if type(value) is int:
        value = str(value)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Missing message indices")
    result: set[int] = set()
    for part in value.split(","):
        match = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+)\s*)?", part)
        if not match:
            raise ValueError("Ambiguous message indices")
        start = int(match[1])
        end = int(match[2]) if match[2] is not None else start
        if not 0 <= start <= end <= 100000 or end - start > 10000:
            raise ValueError("Invalid message range")
        result.update(range(start, end + 1))
    return tuple(sorted(result))


def evermem_sources(rows: list[dict[str, Any]], *, topic: str) -> tuple[ResearchSource, ...]:
    result: list[ResearchSource] = []
    seen: set[str] = set()
    for row in rows:
        if str(row["topic_id"]) != topic:
            raise ValueError("Cross-topic source row")
        day = _day(row["date"])
        for group, messages in row["dialogues"].items():
            if messages is None or messages == []:
                continue
            source_id = f"{topic}/{day}/{_group(group)}"
            if source_id in seen:
                raise ValueError("Duplicate dated group source")
            seen.add(source_id)
            text, mids, speakers = [], [], set()
            for message in messages:
                index = message["message_index"]
                if type(index) is not int or index < 0:
                    raise ValueError("Invalid corpus message index")
                mid = f"{source_id}/{index}"
                if mid in mids:
                    raise ValueError("Duplicate corpus message index")
                mids.append(mid)
                speaker = str(message.get("speaker", ""))
                speakers.add(speaker)
                text.append(f"[{message.get('time', '')}] {speaker}: {message['dialogue']}")
            result.append(ResearchSource(source_id, "\n".join(text), day, "; ".join(sorted(speakers)), tuple(mids)))
    return tuple(result)


def evermem_query(row: dict[str, Any]) -> ResearchQuery:
    topic, qid, text = str(row["topic_id"]), str(row["id"]), row["Q"]
    if not isinstance(text, str) or not text.strip() or not qid:
        raise ValueError("Empty query")
    # All official multiple-choice options are observable query inputs. The
    # separate A field identifying the gold answer is never projected.
    options = row.get("options")
    if options:
        if not isinstance(options, dict) or set(options) != {"A", "B", "C", "D"}:
            raise ValueError("Unrecognized question options")
        if any(not isinstance(value, str) for value in options.values()):
            raise ValueError("Invalid question option type")
        text += "\nOptions:\n" + "\n".join(f"{label}) {options[label]}" for label in sorted(options))
    # This release has no legitimate as-of date; use the full topic history.
    return ResearchQuery(f"{topic}/{qid}", text, topic)


def evermem_judgment(row: dict[str, Any], sources: tuple[ResearchSource, ...]) -> dict[str, tuple[str, ...]]:
    """Evaluator-only gold projection with strict source and message validation."""
    topic = str(row["topic_id"])
    lookup = {s.source_id: set(s.message_ids) for s in sources}
    refs = row["R"]
    if not isinstance(refs, list) or not refs:
        raise ValueError("Empty references")
    result: dict[str, set[str]] = {}
    for ref in refs:
        sid = f"{topic}/{_day(ref['date'])}/{_group(ref['group'])}"
        if sid not in lookup:
            raise ValueError("Reference source absent from corpus")
        ids = {f"{sid}/{index}" for index in message_indices(ref["message_index"])}
        if not ids.issubset(lookup[sid]):
            raise ValueError("Reference message absent from corpus")
        result.setdefault(sid, set()).update(ids)
    return {sid: tuple(sorted(ids)) for sid, ids in sorted(result.items())}
