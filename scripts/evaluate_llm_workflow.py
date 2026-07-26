"""Run a live configured-LLM synthetic workflow evaluation.

The script creates a disposable Telegram-bound user, ingests synthetic entries
through the real LLM pipeline, asks over the stored memory, verifies core
invariants, and removes all synthetic rows/vault files/cache entries.
"""

from __future__ import annotations

import argparse
import asyncio
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
EVAL_STATE = isolate_eval_state(ROOT, "llm-workflow")
from thoughtpins.bot import commands  # noqa: E402
from thoughtpins.bot.commands import answer_with_llm, handle_conversation  # noqa: E402
from thoughtpins.config import config  # noqa: E402
from thoughtpins.data_lifecycle import delete_user_data  # noqa: E402
from thoughtpins.db import ActionItem, Entity, Expense, Memory, RawEntry, User  # noqa: E402
from thoughtpins.ingestion.classify import classify_message  # noqa: E402
from thoughtpins.ingestion.pipeline import process_message  # noqa: E402
from thoughtpins.store import get_session, init_db  # noqa: E402
from thoughtpins.users import get_or_create_user_for_telegram  # noqa: E402


@dataclass
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
    parser = argparse.ArgumentParser(description="Live configured-LLM synthetic workflow evaluation.")
    parser.add_argument("--keep-data", action="store_true", help="Leave synthetic data for manual inspection.")
    parser.add_argument("--json", action="store_true", help="Print full JSON summary.")
    args = parser.parse_args()

    marker = "TPIN_LIVE_EVAL_" + uuid4().hex[:10]
    chat_id = "synthetic-live-eval-" + marker
    summary: dict[str, object] = {"marker": marker, "chat_id": chat_id}
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

        entries = _synthetic_entries(marker)
        summary["classifications"] = {name: classify_message(text) for name, text in entries.items()}

        results = []
        for index, (name, text) in enumerate(entries.items(), start=1):
            result = process_message(
                session,
                text,
                source="telegram",
                telegram_chat_id=chat_id,
                telegram_message_id=f"live-eval-{index}",
                author_user_id="synthetic-evaluator",
            )
            results.append(
                {
                    "name": name,
                    "type": result.get("type"),
                    "entry_id": result.get("entry_id"),
                    "error": result.get("error"),
                }
            )
        summary["stored"] = results

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
        summary["actions"] = [
            {
                "description": item.description,
                "due_at": item.due_at.isoformat() if item.due_at else None,
                "hour": item.due_at.hour if item.due_at else None,
            }
            for item in actions
        ]
        summary["expense_merchants"] = [_merchant_name(session, expense) for expense in expenses]
        summary["memory_samples"] = [memory.text for memory in memories[:12]]
        summary["memory_evidence"] = [
            {
                "text": memory.text,
                "predicate": memory.predicate,
                "confidence": memory.confidence,
                "provenance": memory.source_provenance,
                "metadata": memory.structured_json or {},
            }
            for memory in memories
        ]

        answer = answer_with_llm(
            "What did Dana decide, what reminders are open, and what did Dana spend money on?",
            session,
            user_id=user_id,
        )
        summary["answer"] = answer

        commands.CONVERSATION_CACHE[chat_id] = [
            {"role": "user", "content": "I am trying not to overbuild UI too early."},
            {"role": "assistant", "content": "Reliability and recovery should come first."},
        ]
        update = FakeUpdate(chat_id)
        asyncio.run(handle_conversation(update, "what do you remember about the readiness decision?"))
        summary["chat_reply"] = update.message.replies[0] if update.message.replies else ""

        checks.extend(_build_checks(summary))
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


def _synthetic_entries(marker: str) -> dict[str, str]:
    return {
        "meeting_reminder_expense": (
            f"{marker}: Synthetic tester Dana met Priya at Northstar Cafe today to review the "
            "journal memory roadmap. Dana spent $18.75 on coffee and snacks. Tomorrow at 10am, "
            "remind Dana to draft the privacy policy checklist and send Priya the backend release notes. "
            "Dana decided reliability should come before UI polish."
        ),
        "long_readiness_essay": (
            f"{marker}: Synthetic long essay about launch readiness. "
            + "Founder Telegram use should prove memory-aware chat, reminders, backup recovery, and tenant isolation before UI expansion. "
            * 24
            + "Decision: validate reliability first, then build mobile UI."
        ),
        "social_edge_case": (
            f"{marker}: At the review, Priya said, 'the backup restore path matters more than animation polish.' "
            "Dana felt relieved because the priority was clearer."
        ),
        "rumor_and_retraction": (
            f"{marker}: Friday at Harbor House, Nora told me she had heard from Max that Eli planned "
            "to leave our volunteer group. Nora said she was not sure it was true. Later that evening "
            "Nora texted, 'I got that wrong; Eli is staying.' The earlier claim should be treated as "
            "retracted, not as a fact about Eli."
        ),
        "school_social_causality": (
            f"{marker}: At Founders Hall after debate practice, Ava said, 'I felt sidelined.' She missed "
            "the team dinner because Sam moved rehearsal earlier without telling her. Ava decided to ask "
            "Sam directly what happened before assuming it was intentional."
        ),
        "creative_network_decision": (
            f"{marker}: During the opening at North Gallery, Celia introduced me to Rowan, an editor at "
            "Lattice Review. Celia said Rowan was looking for essays about memory and place. I decided to "
            "send Rowan the harbor draft on Tuesday because it fits that theme."
        ),
    }


def _merchant_name(session, expense: Expense) -> str | None:
    if not expense.merchant_or_place_entity_id:
        return None
    entity = session.query(Entity).filter(Entity.id == expense.merchant_or_place_entity_id).first()
    return entity.canonical_name if entity else None


def _build_checks(summary: dict[str, object]) -> list[Check]:
    classifications = cast(dict[str, dict[str, object]], summary.get("classifications", {}))
    counts = cast(dict[str, int], summary.get("counts", {}))
    actions = cast(list[dict[str, object]], summary.get("actions", []))
    merchants = cast(list[str | None], summary.get("expense_merchants", []))
    answer = str(summary.get("answer", ""))
    chat_reply = str(summary.get("chat_reply", ""))
    evidence = cast(list[dict[str, object]], summary.get("memory_evidence", []))
    metadata = [
        cast(dict[str, object], item.get("metadata", {}))
        for item in evidence
        if isinstance(item.get("metadata", {}), dict)
    ]

    ten_am_actions = [action for action in actions if action.get("hour") == 10]
    combined_actions = [
        action
        for action in actions
        if " and " in str(action.get("description", "")).lower() and action.get("hour") == 10
    ]
    attributed_nora = [item for item in metadata if str(item.get("attributed_to", "")).casefold() == "nora"]
    retracted_nora = [item for item in attributed_nora if str(item.get("claim_status", "")).casefold() == "retracted"]
    orphan_hearsay = [
        item
        for item in metadata
        if str(item.get("epistemic_status", "")).casefold() == "hearsay"
        and not str(item.get("attributed_to", "")).strip()
    ]
    social_places = {str(item.get("place", "")).casefold() for item in metadata if item.get("place")}
    causal_memories = [item for item in metadata if item.get("motivation") or item.get("consequence")]

    return [
        Check(
            "meeting entry classified as journal",
            classifications.get("meeting_reminder_expense", {}).get("type") == "journal_entry",
        ),
        Check(
            "long essay classified as journal",
            classifications.get("long_readiness_essay", {}).get("type") == "journal_entry",
        ),
        Check("all entries stored", counts.get("raw_entries", 0) == 6, str(counts)),
        Check("memories extracted", counts.get("memories", 0) >= 12, str(counts)),
        Check("explicit 10am reminders preserved", len(ten_am_actions) >= 2, str(actions)),
        Check("redundant combined reminder removed", not combined_actions, str(combined_actions)),
        Check("expense merchant linked", "Northstar Cafe" in merchants, str(merchants)),
        Check("speaker attribution survives storage", bool(attributed_nora), str(attributed_nora[:2])),
        Check("retraction survives storage", bool(retracted_nora), str(attributed_nora[:3])),
        Check("hearsay is not orphaned", not orphan_hearsay, str(orphan_hearsay[:3])),
        Check(
            "social place context survives storage",
            bool({"harbor house", "founders hall", "north gallery"} & social_places),
            str(sorted(social_places)),
        ),
        Check("causal context survives storage", bool(causal_memories), str(causal_memories[:2])),
        Check("query answer mentions decision", "reliability" in answer.lower() and "ui" in answer.lower()),
        Check("query answer mentions expense", "18.75" in answer or "coffee" in answer.lower()),
        Check(
            "chat reply uses memory",
            "reliability" in chat_reply.lower() or "backup" in chat_reply.lower(),
            chat_reply[:160],
        ),
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
