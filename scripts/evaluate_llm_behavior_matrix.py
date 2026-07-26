"""Live configured-LLM behavior matrix for journal style coverage.

This creates a disposable Telegram-bound user, ingests a broader set of
synthetic journal styles through the real LLM pipeline, asks memory-aware
questions, validates product invariants, and removes all synthetic rows/files.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
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
EVAL_STATE = isolate_eval_state(ROOT, "behavior-matrix")
from thoughtpins.bot import commands  # noqa: E402
from thoughtpins.bot.commands import answer_with_llm, handle_conversation  # noqa: E402
from thoughtpins.config import config  # noqa: E402
from thoughtpins.data_lifecycle import delete_user_data  # noqa: E402
from thoughtpins.db import ActionItem, Entity, Expense, Memory, RawEntry, User  # noqa: E402
from thoughtpins.ingestion.classify import classify_message  # noqa: E402
from thoughtpins.ingestion.pipeline import process_message  # noqa: E402
from thoughtpins.store import get_session, init_db  # noqa: E402
from thoughtpins.users import get_or_create_user_for_telegram  # noqa: E402


@dataclass(frozen=True)
class EntryCase:
    name: str
    text: str
    required_terms: tuple[str, ...] = ()
    forbidden_action_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str = ""


class FakeChat:
    async def send_action(self, action: str) -> None:
        return None


class FakeMessage:
    def __init__(self, chat_id: str):
        self.chat_id = chat_id
        self.chat = FakeChat()
        self.replies: list[str] = []

    async def reply_text(self, text: str, **kwargs) -> None:
        self.replies.append(text)


class FakeUpdate:
    def __init__(self, chat_id: str):
        self.message = FakeMessage(chat_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="Live configured-LLM broad behavior matrix.")
    parser.add_argument("--keep-data", action="store_true", help="Leave synthetic data for manual inspection.")
    parser.add_argument("--json", action="store_true", help="Print full JSON summary.")
    args = parser.parse_args()

    marker = "TPIN_MATRIX_EVAL_" + uuid4().hex[:10]
    chat_id = "synthetic-matrix-eval-" + marker
    summary: dict[str, Any] = {"marker": marker, "chat_id": chat_id}
    checks: list[Check] = []
    user_id: str | None = None

    init_db()
    session = get_session()
    try:
        user = get_or_create_user_for_telegram(chat_id, session=session)
        user_id = user.id
        summary["user"] = {
            "id": user_id,
            "auth_method": user.auth_method,
            "telegram_bound": user.telegram_chat_id == chat_id,
        }

        cases = _entry_cases(marker)
        summary["classification_only"] = _classification_only_cases()
        summary["classifications"] = {case.name: classify_message(case.text) for case in cases}

        stored: list[dict[str, Any]] = []
        for index, case in enumerate(cases, start=1):
            result = process_message(
                session,
                case.text,
                source="telegram",
                telegram_chat_id=chat_id,
                telegram_message_id=f"matrix-eval-{index}",
                author_user_id="synthetic-evaluator",
            )
            stored.append(
                {
                    "name": case.name,
                    "type": result.get("type"),
                    "entry_id": result.get("entry_id"),
                    "stats": result.get("stats"),
                    "error": result.get("error"),
                }
            )
        summary["stored"] = stored

        session.expire_all()
        raw_entries = session.query(RawEntry).filter(RawEntry.user_id == user_id).all()
        memories = session.query(Memory).filter(Memory.user_id == user_id).all()
        actions = (
            session.query(ActionItem)
            .filter(ActionItem.user_id == user_id)
            .order_by(ActionItem.due_at.is_(None), ActionItem.due_at, ActionItem.description)
            .all()
        )
        expenses = session.query(Expense).filter(Expense.user_id == user_id).all()
        entities = session.query(Entity).filter(Entity.user_id == user_id).all()
        summary["counts"] = {
            "raw_entries": len(raw_entries),
            "memories": len(memories),
            "actions": len(actions),
            "expenses": len(expenses),
            "entities": len(entities),
        }
        summary["entry_memory_counts"] = _entry_memory_counts(session, stored)
        summary["memory_samples"] = [memory.text for memory in memories[:100]]
        summary["actions"] = [
            {
                "description": item.description,
                "due_at": item.due_at.isoformat() if item.due_at else None,
                "hour": item.due_at.hour if item.due_at else None,
            }
            for item in actions
        ]
        summary["expenses"] = [
            {
                "amount": expense.amount,
                "currency": expense.currency,
                "merchant": _merchant_name(session, expense),
                "reason": expense.reason,
            }
            for expense in expenses
        ]
        summary["entities"] = [{"name": entity.canonical_name, "type": entity.type} for entity in entities[:80]]

        summary["answers"] = {
            "places_money": answer_with_llm(
                "What places did these entries mention and what did I spend money on?",
                session,
                user_id=user_id,
            ),
            "spiritual_business": answer_with_llm(
                "What spiritual or philosophical thread showed up, and what business idea did I have?",
                session,
                user_id=user_id,
            ),
            "open_loops": answer_with_llm(
                "What open reminders or concrete next steps are in this set?",
                session,
                user_id=user_id,
            ),
        }

        commands.CONVERSATION_CACHE[chat_id] = [
            {"role": "user", "content": "I feel scattered after a lot of different notes today."},
            {"role": "assistant", "content": "Let's look for the pattern across the day."},
        ]
        update = FakeUpdate(chat_id)
        asyncio.run(handle_conversation(update, "what pattern do you see across my notes today?"))
        summary["chat_reply"] = update.message.replies[0] if update.message.replies else ""

        checks.extend(_build_checks(cases, summary))
    finally:
        if not args.keep_data:
            summary["cleanup"] = _cleanup(session, user_id, chat_id, marker)
        else:
            session.close()
            summary["cleanup"] = {"kept": True}

    summary["checks"] = [check.__dict__ for check in checks]
    if args.json:
        print(json.dumps(summary, indent=2, default=str))
    else:
        for check in checks:
            status = "PASS" if check.passed else "FAIL"
            detail = f" - {check.detail}" if check.detail else ""
            print(f"{status}: {check.name}{detail}")
        print(f"Summary: {sum(check.passed for check in checks)}/{len(checks)} passed")
    return 0 if all(check.passed for check in checks) else 1


def _entry_cases(marker: str) -> list[EntryCase]:
    long_reflection = (
        f"{marker}: Deep contemplative journal. I woke up with a heavy quiet feeling and kept circling the same question: "
        "whether ambition is still clean when it is partly driven by fear. "
        "The honest thread was that discipline feels more peaceful when it is tied to service instead of proving myself. "
        "Prayer felt less like asking for outcomes and more like aligning attention. "
        "I want the memory layer to hold these inner patterns without turning every reflection into a task. "
    )
    long_reflection += (
        "The day had a strange mix of humility, resolve, and caution. "
        "I kept thinking that a durable app should protect the user from performance theater and help them remember what is true. "
    ) * 12

    return [
        EntryCase(
            name="bar_quick_note",
            text=(
                f"{marker}: Quick bar note from Green Bar. Met Jordan after work, had one pilsner, "
                "and spent $12 on the drink. The conversation was loose but useful: Jordan said my launch plan "
                "sounds calmer when I talk about reliability instead of hype."
            ),
            required_terms=("Green Bar", "Jordan", "reliability"),
        ),
        EntryCase(
            name="coffee_chat_longer",
            text=(
                f"{marker}: Coffee chat at Blue Bottle with Maya. We talked for almost two hours about the journal app, "
                "privacy, and why memory should feel like a trusted friend instead of a dashboard. I spent $7.20 at Blue Bottle "
                "on a cortado. Maya said, 'make the quiet version work before the impressive version.' Tomorrow at 3pm, "
                "remind me to text Maya the privacy-safe demo notes."
            ),
            required_terms=("Blue Bottle", "Maya", "trusted friend"),
        ),
        EntryCase(
            name="deep_contemplative_journal",
            text=long_reflection,
            required_terms=("ambition", "prayer", "service"),
            forbidden_action_terms=("protect the user", "remember what is true"),
        ),
        EntryCase(
            name="quick_daily_random_thought",
            text=(
                f"{marker}: Random thought: attention feels like compound interest. "
                "A tiny good habit seems invisible until it suddenly becomes identity."
            ),
            required_terms=("attention", "compound interest", "habit"),
        ),
        EntryCase(
            name="business_idea",
            text=(
                f"{marker}: Business idea: a universal memory layer for founders that starts in Telegram, "
                "then becomes a mobile app once ingestion, search, reminders, export, and deletion are trustworthy. "
                "The wedge is personal use first, platform later."
            ),
            required_terms=("memory layer", "Telegram", "mobile app"),
            forbidden_action_terms=("platform later",),
        ),
        EntryCase(
            name="spiritual_philosophical_bit",
            text=(
                f"{marker}: Spiritual note: surrender today felt less like quitting and more like refusing to worship outcomes. "
                "The useful philosophical bit is that agency and humility are not opposites."
            ),
            required_terms=("surrender", "agency", "humility"),
        ),
        EntryCase(
            name="messy_social_edge_case",
            text=(
                f"{marker}: Small social read: Lina looked distracted during the coworking session, but when I asked she said "
                "she was just worried about her brother's move. I should not overinterpret it. The room at Union Workspace "
                "felt productive but a little tense."
            ),
            required_terms=("Lina", "Union Workspace", "overinterpret"),
            forbidden_action_terms=("overinterpret",),
        ),
        EntryCase(
            name="explicit_reminder_and_errand",
            text=(
                f"{marker}: Quick errand note: picked up groceries at FreshMart for $34.18. "
                "Tomorrow at 8am remind me to send the apartment maintenance email."
            ),
            required_terms=("FreshMart", "groceries", "apartment maintenance"),
        ),
    ]


def _classification_only_cases() -> dict[str, dict[str, Any]]:
    examples = {
        "casual_greeting": "what's up bro",
        "status_check": "everything running?",
        "explicit_query": "what did I say about Maya?",
        "short_note_prefix": "random thought: attention is fuel",
        "business_note_prefix": "business idea: memory for founders",
        "spiritual_note_prefix": "spiritual note: humility helped today",
    }
    return {name: classify_message(text) for name, text in examples.items()}


def _entry_memory_counts(session, stored: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in stored:
        entry_id = item.get("entry_id")
        if not entry_id:
            counts[item["name"]] = 0
            continue
        counts[item["name"]] = session.query(Memory).filter(Memory.raw_entry_id == entry_id).count()
    return counts


def _merchant_name(session, expense: Expense) -> str | None:
    if not expense.merchant_or_place_entity_id:
        return None
    entity = session.query(Entity).filter(Entity.id == expense.merchant_or_place_entity_id).first()
    return entity.canonical_name if entity else None


def _build_checks(cases: list[EntryCase], summary: dict[str, Any]) -> list[Check]:
    classifications = cast(dict[str, dict[str, Any]], summary.get("classifications", {}))
    classification_only = cast(dict[str, dict[str, Any]], summary.get("classification_only", {}))
    stored = cast(list[dict[str, Any]], summary.get("stored", []))
    counts = cast(dict[str, int], summary.get("counts", {}))
    memory_counts = cast(dict[str, int], summary.get("entry_memory_counts", {}))
    memory_samples = "\n".join(cast(list[str], summary.get("memory_samples", []))).lower()
    actions = cast(list[dict[str, Any]], summary.get("actions", []))
    expenses = cast(list[dict[str, Any]], summary.get("expenses", []))
    entities = cast(list[dict[str, Any]], summary.get("entities", []))
    answers = cast(dict[str, str], summary.get("answers", {}))
    chat_reply = str(summary.get("chat_reply", ""))

    all_memories = memory_samples
    all_actions = "\n".join(str(action.get("description", "")) for action in actions).lower()
    expense_merchants = [str(expense.get("merchant") or "") for expense in expenses]
    action_hours = {str(action.get("description", "")).lower(): action.get("hour") for action in actions}

    checks: list[Check] = [
        Check(
            "casual greetings are conversation",
            classification_only.get("casual_greeting", {}).get("type") == "conversation",
            str(classification_only.get("casual_greeting")),
        ),
        Check(
            "status checks are conversation",
            classification_only.get("status_check", {}).get("type") == "conversation",
            str(classification_only.get("status_check")),
        ),
        Check(
            "explicit memory questions are query",
            classification_only.get("explicit_query", {}).get("type") == "query",
            str(classification_only.get("explicit_query")),
        ),
        Check(
            "note prefixes are journal entries",
            all(
                classification_only.get(name, {}).get("type") == "journal_entry"
                for name in ("short_note_prefix", "business_note_prefix", "spiritual_note_prefix")
            ),
            str(
                {
                    name: classification_only.get(name)
                    for name in ("short_note_prefix", "business_note_prefix", "spiritual_note_prefix")
                }
            ),
        ),
        Check(
            "all matrix entries classified as journal",
            all(classifications.get(case.name, {}).get("type") == "journal_entry" for case in cases),
            str(classifications),
        ),
        Check(
            "all matrix entries stored",
            len(stored) == len(cases) and all(item.get("type") == "journal_stored" for item in stored),
            str(stored),
        ),
        Check(
            "each entry produced memories",
            all(memory_counts.get(case.name, 0) >= 1 for case in cases),
            str(memory_counts),
        ),
        Check(
            "memory volume is plausible",
            counts.get("memories", 0) >= len(cases) * 2,
            str(counts),
        ),
        Check(
            "bar and cafe expenses linked to merchants",
            _has_merchant(expense_merchants, "Green Bar")
            and _has_merchant(expense_merchants, "Blue Bottle")
            and _has_merchant(expense_merchants, "FreshMart"),
            str(expenses),
        ),
        Check(
            "explicit 3pm and 8am reminders preserved",
            any("maya" in desc and hour == 15 for desc, hour in action_hours.items())
            and any("maintenance" in desc and hour == 8 for desc, hour in action_hours.items()),
            str(actions),
        ),
        Check(
            "reflection/business notes did not become fake tasks",
            not any(term in all_actions for case in cases for term in case.forbidden_action_terms),
            str(actions),
        ),
        Check(
            "required concepts appear in extracted memories",
            all(term.lower() in all_memories for case in cases for term in case.required_terms),
            "\n".join(cast(list[str], summary.get("memory_samples", []))[:20]),
        ),
        Check(
            "place and expense query uses stored memory",
            all(term in answers.get("places_money", "").lower() for term in ("green bar", "blue bottle", "freshmart")),
            answers.get("places_money", "")[:500],
        ),
        Check(
            "spiritual/business query uses stored memory",
            all(term in answers.get("spiritual_business", "").lower() for term in ("surrender", "memory layer")),
            answers.get("spiritual_business", "")[:500],
        ),
        Check(
            "open loops query stays concrete",
            "maya" in answers.get("open_loops", "").lower()
            and "maintenance" in answers.get("open_loops", "").lower()
            and "surrender" not in answers.get("open_loops", "").lower(),
            answers.get("open_loops", "")[:500],
        ),
        Check(
            "generic concepts are not stored as people",
            not _generic_people(entities),
            str(_generic_people(entities)),
        ),
        Check(
            "conversation reply uses cross-entry pattern",
            any(
                term in chat_reply.lower()
                for term in ("reliability", "quiet", "attention", "memory layer", "surrender")
            ),
            chat_reply[:500],
        ),
    ]
    return checks


def _has_merchant(merchants: list[str], expected: str) -> bool:
    expected_lower = expected.lower()
    return any(expected_lower in merchant.lower() for merchant in merchants)


def _generic_people(entities: list[dict[str, Any]]) -> list[str]:
    generic_names = {
        "agency",
        "ambition",
        "attention",
        "caution",
        "conversation",
        "cortado",
        "day",
        "discipline",
        "fear",
        "groceries",
        "habit",
        "hype",
        "humility",
        "identity",
        "memory",
        "move",
        "outcome",
        "outcomes",
        "pilsner",
        "performance",
        "privacy",
        "prayer",
        "quitting",
        "reliability",
        "resolve",
        "service",
        "social read",
        "spirituality",
        "surrender",
        "the day",
        "the room",
        "truth",
    }
    offenders: list[str] = []
    for entity in entities:
        name = str(entity.get("name") or "").strip()
        entity_type = str(entity.get("type") or "").strip().lower()
        name_lower = name.lower()
        if entity_type != "person":
            continue
        if name_lower in generic_names:
            offenders.append(name)
        elif len(name_lower.split()) >= 3 and not any(token in name_lower for token in ("brother", "sister")):
            offenders.append(name)
    return offenders


def _cleanup(session, user_id: str | None, chat_id: str, marker: str) -> dict[str, Any]:
    cleanup: dict[str, Any] = {"db_deleted": {}, "vault_removed": False, "cache_removed": False}
    try:
        if user_id:
            cleanup["db_deleted"] = delete_user_data(session, user_id)
            cleanup["remaining_db_markers"] = (
                session.query(RawEntry).filter(RawEntry.raw_text.contains(marker)).count()
                + session.query(Memory).filter(Memory.text.contains(marker)).count()
                + session.query(Entity).filter(Entity.canonical_name.contains(marker)).count()
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
