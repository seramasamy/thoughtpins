from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
for path in (SRC_ROOT, SCRIPTS_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from console_output import force_utf8_stdio

from thoughtpins.config import config
from thoughtpins.db import Base, Memory, RawEntry, User
from thoughtpins.ingestion.classify import classify_message
from thoughtpins.library import ingest_document_text
from thoughtpins.memory.corrections import store_and_apply_correction
from thoughtpins.memory.reindex import reindex_vectors
from thoughtpins.memory.search import search
from thoughtpins.store import get_engine, get_session
from thoughtpins.utils import hash_text

force_utf8_stdio()


@dataclass
class EvalCheck:
    name: str
    passed: bool
    detail: str = ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic memory/retrieval quality harness.")
    parser.add_argument(
        "--live-llm", action="store_true", help="Also ask the configured LLM against the seeded scratch memory."
    )
    parser.add_argument("--keep", action="store_true", help="Keep scratch DB/vector files for debugging.")
    args = parser.parse_args()

    scratch_id = uuid4().hex
    db_path = PROJECT_ROOT / ".tmp" / f"memory-quality-{scratch_id}.sqlite3"
    qdrant_path = PROJECT_ROOT / ".tmp" / f"memory-quality-qdrant-{scratch_id}"
    checks: list[EvalCheck] = []

    old_values = _override_config(db_path, qdrant_path)
    try:
        _reset_store()
        Base.metadata.create_all(bind=get_engine())
        session = get_session()
        try:
            user = _seed_user(session)
            _seed_journal_memories(session, user.id)
            source_result = ingest_document_text(
                session,
                (
                    "The saved essay argues that durable memory systems need retrieval evidence, "
                    "correction handling, and source ingestion. It uses the blue lantern marker "
                    "as an obscure recall detail."
                ),
                user_id=user.id,
                source_type="article",
                title="Memory Systems Essay",
            )
            session.commit()
            stats = reindex_vectors(session=session, user_id=user.id, include_private=True, reset=True)

            checks.extend(_classification_checks())
            checks.extend(_retrieval_checks(session, user.id))
            checks.extend(_correction_checks(session, user.id))
            checks.append(
                EvalCheck(
                    "document source indexed",
                    stats.indexed >= 1 and bool(source_result.document_id),
                    str(asdict(stats)),
                )
            )
            checks.extend(_context_checks(session, user.id))
            if args.live_llm:
                checks.extend(_live_llm_checks(session, user.id))
        finally:
            session.close()
    finally:
        _reset_store()
        _restore_config(old_values)
        if not args.keep:
            db_path.unlink(missing_ok=True)
            db_path.with_suffix(db_path.suffix + "-wal").unlink(missing_ok=True)
            db_path.with_suffix(db_path.suffix + "-shm").unlink(missing_ok=True)
            shutil.rmtree(qdrant_path, ignore_errors=True)

    passed = all(check.passed for check in checks)
    print(json.dumps({"passed": passed, "checks": [asdict(check) for check in checks]}, indent=2))
    return 0 if passed else 1


def _override_config(db_path: Path, qdrant_path: Path) -> dict[str, tuple[object, object]]:
    config_cls = type(config)
    keys = [
        "DATABASE_URL",
        "AUTO_CREATE_TABLES",
        "REQUIRE_API_AUTH",
        "VECTOR_MODE",
        "QDRANT_PATH",
        "MEMORY_CONTEXT_MODE",
        "MEMORY_CONTEXT_FULL_INLINE_MAX_CHARS",
        "MEMORY_CONTEXT_MAX_CHARS",
    ]
    old = {key: (getattr(config, key), getattr(config_cls, key)) for key in keys}
    overrides = {
        "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
        "AUTO_CREATE_TABLES": True,
        "REQUIRE_API_AUTH": False,
        "VECTOR_MODE": "qdrant_local",
        "QDRANT_PATH": str(qdrant_path),
        "MEMORY_CONTEXT_MODE": "smart",
        "MEMORY_CONTEXT_FULL_INLINE_MAX_CHARS": 800,
        "MEMORY_CONTEXT_MAX_CHARS": 60_000,
    }
    for key, value in overrides.items():
        setattr(config, key, value)
        setattr(config_cls, key, value)
    return old


def _restore_config(old_values: dict[str, tuple[object, object]]) -> None:
    config_cls = type(config)
    for key, (instance_value, class_value) in old_values.items():
        setattr(config, key, instance_value)
        setattr(config_cls, key, class_value)


def _reset_store() -> None:
    import thoughtpins.store as store
    from thoughtpins.memory.vector_store import close_vector_store

    close_vector_store()
    if store._engine is not None:
        store._engine.dispose()
    store._engine = None
    store._SessionLocal = None


def _seed_user(session) -> User:
    user = User(email="memory-quality@example.local", display_name="Memory Quality Eval")
    session.add(user)
    session.flush()
    return user


def _seed_journal_memories(session, user_id: str) -> None:
    entries = [
        (
            "quick_bar",
            "Quick note from the bar: I met Maya at Green Room and she said the product should feel trustworthy.",
            "Maya said the product should feel trustworthy after a Green Room bar conversation.",
            "conversation",
        ),
        (
            "coffee_chat",
            "Longer coffee chat with Leo: we discussed an offline-first journal and the copper bridge marker.",
            "Leo discussed an offline-first journal and the copper bridge marker over coffee.",
            "idea",
        ),
        (
            "spiritual",
            "Small spiritual note: patience felt like attention without bargaining.",
            "The user framed patience as attention without bargaining.",
            "reflection",
        ),
        (
            "business",
            "Business idea: premium memory layer for founders, starting with Telegram as the test client.",
            "The user considered a premium founder memory layer with Telegram as the test client.",
            "business_idea",
        ),
        (
            "old_wrong",
            "Steve's kid is Jeff.",
            "Steve's kid is Jeff.",
            "relationship",
        ),
    ]
    for label, raw_text, memory_text, memory_type in entries:
        raw = RawEntry(
            user_id=user_id,
            source="eval",
            raw_text=raw_text,
            content_hash=hash_text(label + raw_text),
            processed_status="completed",
            sensitivity="personal",
        )
        session.add(raw)
        session.flush()
        session.add(
            Memory(
                user_id=user_id,
                raw_entry_id=raw.id,
                memory_type=memory_type,
                text=memory_text,
                sensitivity="personal",
                confidence="observed_by_user",
                source_provenance=f"raw_entry:{raw.id}",
            )
        )
    session.commit()


def _classification_checks() -> list[EvalCheck]:
    cases = [
        ("casual chat", "whats up bro", "conversation"),
        ("forced save", "save: quick thought from a bar", "journal_entry"),
        ("article link", "read: https://example.com/story", "document_link"),
        ("correction", "Actually Steve's kid is Geoff, not Jeff", "correction"),
        ("ambiguous thought", "I think memory is strange", "ambiguous"),
    ]
    return [
        EvalCheck(name, classify_message(text).get("type") == expected, f"{text} -> {classify_message(text)}")
        for name, text, expected in cases
    ]


def _retrieval_checks(session, user_id: str) -> list[EvalCheck]:
    cases = [
        ("bar trust recall", "what did Maya say at the bar?", "trustworthy"),
        ("obscure coffee marker", "what was the copper bridge marker?", "copper bridge"),
        ("spiritual phrasing", "what did I say patience felt like?", "attention without bargaining"),
        ("document obscure marker", "what was the blue lantern marker?", "blue lantern"),
    ]
    checks: list[EvalCheck] = []
    for name, query, expected in cases:
        results = search(query, session=session, user_id=user_id, include_private=True, limit=5)
        haystack = "\n".join(result.text for result in results).lower()
        checks.append(
            EvalCheck(name, expected.lower() in haystack, f"top={[(r.memory_type, r.text[:80]) for r in results[:3]]}")
        )
    return checks


def _correction_checks(session, user_id: str) -> list[EvalCheck]:
    result = store_and_apply_correction(
        session,
        "Actually Steve's kid is Geoff, not Jeff",
        user_id=user_id,
        source="eval",
    )
    results = search("who is Steve's kid?", session=session, user_id=user_id, include_private=True, limit=5)
    haystack = "\n".join(result.text for result in results).lower()
    return [
        EvalCheck(
            "correction superseded old memory", bool(result.superseded_memory_ids), str(result.superseded_memory_ids)
        ),
        EvalCheck("correction retrieval prefers new fact", "geoff" in haystack, haystack[:500]),
        EvalCheck("old correction target inactive", "steve's kid is jeff." not in haystack, haystack[:500]),
    ]


def _context_checks(session, user_id: str) -> list[EvalCheck]:
    from thoughtpins.bot.commands import build_memory_context_package

    context = build_memory_context_package(
        "what did Maya say and what was the blue lantern marker?",
        session,
        user_id=user_id,
        include_private=True,
        include_vault=False,
    )
    return [
        EvalCheck(
            "smart context includes source section", "QUERY-RELEVANT MEMORIES AND SOURCES" in context, context[:300]
        ),
        EvalCheck("smart context includes evidence ids", "id=" in context and "source=" in context, context[:500]),
        EvalCheck("smart context includes document detail", "blue lantern marker" in context.lower(), context[:500]),
    ]


def _live_llm_checks(session, user_id: str) -> list[EvalCheck]:
    from thoughtpins.bot.commands import answer_with_llm

    answer = answer_with_llm(
        "What did Maya say at the bar, and what article marker should I remember?",
        session,
        include_private=True,
        user_id=user_id,
    )
    lowered = answer.lower()
    return [
        EvalCheck("live llm mentions Maya trust detail", "trustworthy" in lowered, answer[:800]),
        EvalCheck("live llm mentions document marker", "blue lantern" in lowered, answer[:800]),
    ]


if __name__ == "__main__":
    raise SystemExit(main())
