"""Live configured-LLM evaluation for natural Telegram note variety.

Creates a disposable Telegram-bound user, ingests representative founder-style
messages through the real processing path, verifies retrieval/answer behavior,
and deletes its own rows, vector points, vault files, and chat cache.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for path in (SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from console_output import force_utf8_stdio  # noqa: E402
from eval_runtime import cleanup_eval_state, isolate_eval_state  # noqa: E402

force_utf8_stdio()
EVAL_STATE = isolate_eval_state(ROOT, "telegram-note-variety")
from thoughtpins.bot import commands  # noqa: E402
from thoughtpins.bot.commands import answer_with_llm  # noqa: E402
from thoughtpins.config import config  # noqa: E402
from thoughtpins.data_lifecycle import delete_user_data  # noqa: E402
from thoughtpins.db import Memory, RawEntry, User  # noqa: E402
from thoughtpins.ingestion.classify import classify_message  # noqa: E402
from thoughtpins.ingestion.pipeline import process_message  # noqa: E402
from thoughtpins.memory.search import search  # noqa: E402
from thoughtpins.store import get_session, init_db  # noqa: E402
from thoughtpins.users import get_or_create_user_for_telegram  # noqa: E402


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Live Telegram note-variety workflow evaluation.")
    parser.add_argument("--keep-data", action="store_true", help="Leave synthetic data for manual inspection.")
    parser.add_argument("--json", action="store_true", help="Print full JSON summary.")
    args = parser.parse_args()

    marker = "TPIN_NOTE_VARIETY_" + uuid4().hex[:10]
    chat_id = "synthetic-note-variety-" + marker
    user_id: str | None = None
    summary: dict[str, object] = {"marker": marker, "chat_id": chat_id}
    checks: list[Check] = []

    init_db()
    session = get_session()
    try:
        user = get_or_create_user_for_telegram(chat_id, session=session)
        user_id = user.id
        entries = _entries(marker)
        summary["classifications"] = {name: classify_message(text) for name, text in entries.items()}
        stored = []
        for index, (name, text) in enumerate(entries.items(), start=1):
            result = process_message(
                session,
                text,
                source="telegram",
                telegram_chat_id=chat_id,
                telegram_message_id=f"note-variety-{index}",
                author_user_id="synthetic-note-variety",
            )
            stored.append(
                {
                    "name": name,
                    "type": result.get("type"),
                    "entry_id": result.get("entry_id"),
                    "error": result.get("error"),
                }
            )
        summary["stored"] = stored

        session.expire_all()
        raw_count = session.query(RawEntry).filter(RawEntry.user_id == user_id).count()
        memory_count = session.query(Memory).filter(Memory.user_id == user_id).count()
        summary["counts"] = {"raw_entries": raw_count, "memories": memory_count}
        summary["retrieval"] = _run_retrieval_checks(session, user_id)
        summary["answer"] = answer_with_llm(
            (
                "Using my notes, summarize the date night, recipe idea, networking contact, "
                "business idea, spiritual thought, and long reflective journal point."
            ),
            session,
            user_id=user_id,
        )
        checks = _build_checks(summary)
    finally:
        if not args.keep_data:
            cleanup = _cleanup(session, user_id, chat_id, marker)
            summary["cleanup"] = cleanup
        else:
            session.close()
            summary["cleanup"] = {"kept": True}

    passed = all(check.passed for check in checks)
    summary["checks"] = [check.__dict__ for check in checks]
    if args.json:
        print(json.dumps(summary, indent=2, default=str))
    else:
        for check in checks:
            status = "PASS" if check.passed else "FAIL"
            suffix = f" - {check.detail}" if check.detail else ""
            print(f"{status}: {check.name}{suffix}")
        print(f"Summary: {sum(check.passed for check in checks)}/{len(checks)} passed")
    return 0 if passed else 1


def _entries(marker: str) -> dict[str, str]:
    return {
        "quick_bar_note": (
            f"{marker}: Quick note from the bar: I met Lina at Ember Room, and she recommended "
            "the rosemary rye sour. The useful detail was that she trusts products with visible "
            "recovery paths."
        ),
        "date_night_note": (
            f"{marker}: Date night note: we had ramen at Koyo, split the black sesame pudding, "
            "and talked about renting near Riverside Park in the fall."
        ),
        "networking_event_note": (
            f"{marker}: Networking event note: met Priya Shah from Verdant Compliance. She is "
            "looking for local-first audit tooling and cares about offline access."
        ),
        "recipe_note": (
            f"{marker}: Recipe idea: roast carrots with tahini, lemon, cilantro, pistachios, "
            "and a little chili crisp. Try it with chickpeas for protein."
        ),
        "business_idea": (
            f"{marker}: Business idea: a local-first memory app that shows why it recalled a "
            "fact, with exact evidence IDs and a correction trail."
        ),
        "spiritual_note": (
            f"{marker}: Spiritual note: prayer felt less like asking for outcomes and more like "
            "listening without bargaining."
        ),
        "random_daily_thought": (
            f"{marker}: Random thought: attention is a budget, not a mood, so protect the first "
            "ninety minutes of the day."
        ),
        "long_reflective_journal": (
            f"{marker}: Deep contemplative journal: today I noticed that the urge to overbuild "
            "usually appears when the product direction feels emotionally important. The better "
            "move is to make the memory layer exact, inspectable, and calm before polishing UI. "
            "If the system can remember obscure details like the rosemary rye sour, the Koyo "
            "ramen conversation, Priya's offline audit tooling need, and the tahini carrot recipe, "
            "then the app has earned the right to become a broader platform."
        ),
    }


def _run_retrieval_checks(session, user_id: str) -> dict[str, str]:
    queries = {
        "bar drink": "rosemary rye sour",
        "date night": "koyo",
        "networking contact": "priya",
        "recipe": "tahini",
        "business idea": "evidence",
        "spiritual thought": "listening",
        "daily thought": "ninety minutes",
    }
    output = {}
    for name, query in queries.items():
        results = search(query, session=session, user_id=user_id, include_private=True, limit=5)
        output[name] = "\n".join(result.text for result in results[:3])
    return output


def _build_checks(summary: dict[str, object]) -> list[Check]:
    classifications = cast(dict[str, dict[str, object]], summary.get("classifications", {}))
    counts = cast(dict[str, int], summary.get("counts", {}))
    retrieval = cast(dict[str, str], summary.get("retrieval", {}))
    answer = str(summary.get("answer", "")).lower()
    stored = cast(list[dict[str, object]], summary.get("stored", []))

    return [
        Check(
            "all generated examples classified as journal",
            all(item.get("type") == "journal_entry" for item in classifications.values()),
            str(classifications),
        ),
        Check("all generated examples stored", counts.get("raw_entries") == 8, str(counts)),
        Check("memories extracted from examples", counts.get("memories", 0) >= 8, str(counts)),
        Check("no processing errors", all(not item.get("error") for item in stored), str(stored)),
        Check("bar note retrievable", "rosemary rye sour" in retrieval.get("bar drink", "").lower()),
        Check("date night retrievable", "koyo" in retrieval.get("date night", "").lower()),
        Check("networking note retrievable", "priya" in retrieval.get("networking contact", "").lower()),
        Check("recipe retrievable", "tahini" in retrieval.get("recipe", "").lower()),
        Check("business idea retrievable", "evidence" in retrieval.get("business idea", "").lower()),
        Check("spiritual thought retrievable", "listening" in retrieval.get("spiritual thought", "").lower()),
        Check("daily thought retrievable", "ninety minutes" in retrieval.get("daily thought", "").lower()),
        Check("answer mentions date night", "koyo" in answer or "ramen" in answer),
        Check("answer mentions recipe", "tahini" in answer or "carrot" in answer),
        Check("answer mentions networking contact", "priya" in answer or "compliance" in answer),
        Check("answer mentions spiritual thought", "listening" in answer or "bargaining" in answer),
    ]


def _cleanup(session, user_id: str | None, chat_id: str, marker: str) -> dict[str, object]:
    cleanup: dict[str, object] = {"db_deleted": {}, "vault_removed": False, "cache_removed": False}
    try:
        if user_id:
            cleanup["db_deleted"] = delete_user_data(session, user_id)
            cleanup["remaining_db_markers"] = (
                session.query(RawEntry).filter(RawEntry.raw_text.contains(marker)).count()
                + session.query(Memory).filter(Memory.text.contains(marker)).count()
                + session.query(User).filter(User.telegram_chat_id == chat_id).count()
            )
    finally:
        session.close()

    if user_id:
        vault_root = config.vault_path().resolve()
        vault_user_dir = (vault_root / user_id).resolve()
        if vault_user_dir.exists() and vault_root in vault_user_dir.parents:
            shutil.rmtree(vault_user_dir)
            cleanup["vault_removed"] = True

    commands.CONVERSATION_CACHE.pop(chat_id, None)
    commands._save_conversation_cache()
    cleanup["cache_removed"] = True
    try:
        from thoughtpins.memory.vector_store import close_vector_store

        close_vector_store()
        cleanup["vector_store_closed"] = True
    except Exception as exc:
        cleanup["vector_store_close_error"] = str(exc)
    cleanup["eval_state_removed"] = cleanup_eval_state(EVAL_STATE)
    return cleanup


if __name__ == "__main__":
    raise SystemExit(main())
