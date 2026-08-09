"""Execution and formatting for natural chat actions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy.orm import Session

from thoughtpins.chat.capture_summary import format_capture_summary
from thoughtpins.chat.entry_demotion import demote_entry_to_chat
from thoughtpins.chat.importance_actions import execute_importance_action
from thoughtpins.chat.memory_answer import answer_with_llm
from thoughtpins.chat.models import ChatEngineResult, ChatRouteDecision
from thoughtpins.chat.natural_commands import NaturalCommandRoute, confirmation_prompt
from thoughtpins.chat.store import create_pending_action
from thoughtpins.chat.style_memory import CHAT_STATUS, record_user_style_sample
from thoughtpins.config import config
from thoughtpins.crypto import maybe_decrypt_text
from thoughtpins.db import ChatConversation, RawEntry
from thoughtpins.importance import (
    importance_label,
    importance_prompts_enabled,
    should_prompt_for_importance,
)
from thoughtpins.ingestion.pipeline import process_message
from thoughtpins.jobs import dispatch_ingestion_job, get_or_create_ingestion_job
from thoughtpins.library import ingest_document_text, ingest_url, list_documents
from thoughtpins.memory.context_package import _format_context_diagnostics, describe_memory_context_package
from thoughtpins.memory.search import search
from thoughtpins.memory.store import MemoryStore
from thoughtpins.memory.vector_refresh import refresh_vectors_after_removed_memories
from thoughtpins.utils import hash_text, local_today
from thoughtpins.voice_archive import delete_voice_assets_for_entry


@dataclass(frozen=True)
class ActionHooks:
    """Side-effect boundaries used by the chat orchestrator.

    Explicit hooks keep action execution deterministic in tests and let clients
    preserve compatibility adapters without mutating process-wide module state.
    """

    process_message: Callable[..., dict[str, Any]]
    refresh_vectors: Callable[..., None]
    describe_context: Callable[..., dict[str, Any]]
    format_context: Callable[[dict[str, Any]], str]


@dataclass(frozen=True)
class _NaturalActionExecution:
    session: Session
    decision: ChatRouteDecision
    user_id: str
    conversation_key: str
    source: str
    pending_action_id: str | None
    hooks: ActionHooks


def _default_hooks() -> ActionHooks:
    return ActionHooks(
        process_message=process_message,
        refresh_vectors=refresh_vectors_after_removed_memories,
        describe_context=describe_memory_context_package,
        format_context=_format_context_diagnostics,
    )


def _execute_natural_route(
    session: Session,
    route: NaturalCommandRoute,
    *,
    decision: ChatRouteDecision,
    user_id: str,
    conversation: ChatConversation,
    conversation_key: str,
    source: str,
    confirm_action: bool,
    pending_action_id: str | None = None,
    hooks: ActionHooks | None = None,
) -> ChatEngineResult:
    hooks = hooks or _default_hooks()
    if route.needs_confirmation and not confirm_action:
        return _confirmation_required_result(
            session,
            conversation,
            route,
            decision=decision,
            user_id=user_id,
        )

    action = route.action
    args = list(route.args)
    execution = _NaturalActionExecution(
        session=session,
        decision=decision,
        user_id=user_id,
        conversation_key=conversation_key,
        source=source,
        pending_action_id=pending_action_id,
        hooks=hooks,
    )
    special_result = _execute_special_natural_action(execution, action, args)
    if special_result:
        return special_result
    reply = _simple_natural_action_reply(execution, action, args)
    return ChatEngineResult(
        status="replied",
        route_type="natural_command",
        reply=reply,
        metadata=_classification_meta(decision) | {"action": action, "args": args},
    )


def _confirmation_required_result(
    session: Session,
    conversation: ChatConversation,
    route: NaturalCommandRoute,
    *,
    decision: ChatRouteDecision,
    user_id: str,
) -> ChatEngineResult:
    prompt = confirmation_prompt(route)
    pending = create_pending_action(
        session,
        conversation,
        user_id=user_id,
        route=route,
        prompt=prompt,
        metadata=_classification_meta(decision),
    )
    return ChatEngineResult(
        status="confirmation_required",
        route_type="natural_command",
        reply=prompt,
        requires_confirmation=True,
        confirmation_prompt=prompt,
        metadata=_classification_meta(decision)
        | {
            "action": route.action,
            "args": list(route.args),
            "pending_action_id": pending.id,
            "expires_at_utc": pending.expires_at_utc.isoformat() if pending.expires_at_utc else None,
        },
    )


def _simple_natural_action_reply(
    execution: _NaturalActionExecution,
    action: str,
    args: list[str],
) -> str:
    session = execution.session
    user_id = execution.user_id
    if action == "help":
        return (
            "Just type naturally. I can chat, save journal notes, ingest article links/documents, "
            "search memory, undo, and answer from your past context."
        )
    if action == "status":
        stats = MemoryStore(session, user_id=user_id).get_stats()
        return (
            f"System is reachable. Entries: {stats.get('raw_entries', 0)}, "
            f"memories: {stats.get('memories', 0)}, entities: {stats.get('entities', 0)}."
        )
    if action == "memory":
        stats = MemoryStore(session, user_id=user_id).get_stats()
        return (
            f"Memory has {stats.get('memories', 0)} memories across "
            f"{stats.get('entities', 0)} entities from {stats.get('raw_entries', 0)} entries."
        )
    if action == "recent":
        return _format_recent_entries(session, user_id=user_id)
    if action == "today":
        return _format_today_entries(session, user_id=user_id)
    if action in {"search", "candidate_delete_search"}:
        return _format_search_results(session, " ".join(args).strip(), user_id=user_id)
    if action == "context_why":
        query = " ".join(args[1:] if args and args[0].lower() == "why" else args).strip()
        return _format_context_diagnostics_reply(
            session,
            query,
            user_id=user_id,
            conversation_key=execution.conversation_key,
            hooks=execution.hooks,
        )
    if action == "source":
        return _format_source_detail(session, " ".join(args).strip(), user_id=user_id)
    if action == "library":
        return _format_library(session, user_id=user_id)
    if action == "audit":
        return _format_audit_reply(session, user_id=user_id)
    if action == "report":
        return answer_with_llm(" ".join(args).strip() or "summary", session, user_id=user_id)
    return "I understand that request, but this client surface does not expose that operation yet."


def _execute_special_natural_action(
    execution: _NaturalActionExecution,
    action: str,
    args: list[str],
) -> ChatEngineResult | None:
    importance_result = execute_importance_action(
        action,
        execution.session,
        args=args,
        user_id=execution.user_id,
        conversation_key=execution.conversation_key,
        classification_metadata=_classification_meta(execution.decision),
    )
    if importance_result:
        return importance_result
    handler = {
        "doctor": _doctor_action,
        "undo": _undo_action,
        "mark_chat": _mark_chat_action,
        "save_last_chat": _save_last_chat_action,
    }.get(action)
    return handler(execution, args) if handler else None


def _doctor_action(execution: _NaturalActionExecution, args: list[str]) -> ChatEngineResult:
    reply, ok = _format_doctor_reply(
        execution.session,
        user_id=execution.user_id,
        conversation_key=execution.conversation_key,
    )
    return ChatEngineResult(
        status="replied",
        route_type="natural_command",
        reply=reply,
        metadata=_classification_meta(execution.decision)
        | {
            "action": "doctor",
            "args": args,
            "doctor_ok": ok,
            "pending_action_id": execution.pending_action_id,
        },
    )


def _undo_action(execution: _NaturalActionExecution, _args: list[str]) -> ChatEngineResult:
    reply, metadata = _undo_latest(
        execution.session,
        user_id=execution.user_id,
        conversation_key=execution.conversation_key,
        hooks=execution.hooks,
    )
    return ChatEngineResult(
        status="undone",
        route_type="natural_command",
        reply=reply,
        metadata=_classification_meta(execution.decision)
        | metadata
        | {"pending_action_id": execution.pending_action_id},
    )


def _mark_chat_action(execution: _NaturalActionExecution, _args: list[str]) -> ChatEngineResult:
    reply, metadata = _mark_latest_as_chat(
        execution.session,
        user_id=execution.user_id,
        conversation_key=execution.conversation_key,
        hooks=execution.hooks,
    )
    return ChatEngineResult(
        status="marked_chat",
        route_type="natural_command",
        reply=reply,
        metadata=_classification_meta(execution.decision) | metadata,
    )


def _save_last_chat_action(execution: _NaturalActionExecution, args: list[str]) -> ChatEngineResult:
    latest = _latest_chat_entry(
        execution.session,
        user_id=execution.user_id,
        conversation_key=execution.conversation_key,
    )
    if not latest:
        return ChatEngineResult(
            status="replied",
            route_type="natural_command",
            reply="I could not find a recent chat message to save as a journal entry.",
            metadata=_classification_meta(execution.decision) | {"action": "save_last_chat", "args": args},
        )
    stored = _save_journal_turn(
        execution.session,
        maybe_decrypt_text(latest.raw_text),
        user_id=execution.user_id,
        source=execution.source,
        conversation_key=execution.conversation_key,
        message_id="",
        author_user_id=execution.user_id,
        hooks=execution.hooks,
    )
    return ChatEngineResult(
        status=stored.status,
        route_type="natural_command",
        reply=stored.reply,
        entry_id=stored.entry_id,
        job_id=stored.job_id,
        metadata=_classification_meta(execution.decision) | stored.metadata,
    )


def _save_journal_turn(
    session: Session,
    text: str,
    *,
    user_id: str,
    source: str,
    conversation_key: str,
    message_id: str,
    author_user_id: str,
    hooks: ActionHooks | None = None,
) -> ChatEngineResult:
    hooks = hooks or _default_hooks()
    record_user_style_sample(session, user_id=user_id, text=text)
    if config.PROCESS_ENTRIES_ASYNC:
        dedup_material = f"{conversation_key}\n{message_id}"
        dedup_key = f"chat:{source}:{hash_text(dedup_material)}" if message_id else None
        job, _created = get_or_create_ingestion_job(
            session,
            user_id=user_id,
            text=text,
            source=source,
            metadata={
                "conversation_key": conversation_key,
                "message_id": message_id,
                **({"dedup_key": dedup_key} if dedup_key else {}),
            },
            dedup_key=dedup_key,
        )
        dispatch_ingestion_job(session, job, user_id=user_id)
        session.refresh(job)
        return ChatEngineResult(
            status="queued",
            route_type="journal_entry",
            reply="Saved. Processing in the background.",
            job_id=job.id,
            metadata={"job_id": job.id},
        )

    result = hooks.process_message(
        session,
        text,
        user_id=user_id,
        source=source,
        telegram_message_id=message_id,
        telegram_chat_id=conversation_key,
        author_user_id=author_user_id,
    )
    stats = result.get("stats", {})
    if result["type"] == "duplicate":
        return ChatEngineResult(
            status="duplicate",
            route_type="journal_entry",
            reply="Already saved recently. I skipped the duplicate.",
            entry_id=result.get("entry_id"),
            metadata={"result_type": result["type"]},
        )
    if result["type"] == "queued":
        reply = "Saved. The AI service is temporarily unavailable, so extraction is queued for retry."
    elif result["type"] == "error":
        reply = "Saved the raw entry, but AI extraction failed. Use status/doctor for details."
    elif result["type"] == "private_stored":
        reply = "Saved privately."
    else:
        reply = f"Saved. Captured: {format_capture_summary(stats)}."
    importance = result.get("user_importance")
    if importance is not None:
        reply += f" Importance: {importance_label(importance)}."
    elif (
        result.get("entry_id")
        and importance_prompts_enabled(session, user_id=user_id)
        and should_prompt_for_importance(text, stats)
    ):
        reply += "\n\nOptional: rate this entry from 1 to 5 whenever it feels useful."
    return ChatEngineResult(
        status="ok" if result["type"] == "journal_stored" else result["type"],
        route_type="journal_entry",
        reply=reply,
        entry_id=result.get("entry_id"),
        metadata={
            "stats": stats,
            "result_type": result["type"],
            "user_importance": importance,
            "importance_prompted": (
                importance is None
                and bool(result.get("entry_id"))
                and importance_prompts_enabled(session, user_id=user_id)
                and should_prompt_for_importance(text, stats)
            ),
        },
    )


def _ingest_document(session: Session, text: str, *, user_id: str, conversation_key: str, msg_type: str):
    urls = _extract_urls(text)
    if msg_type == "document_link" and urls:
        return ingest_url(
            session,
            urls[0],
            user_id=user_id,
            telegram_chat_id=conversation_key,
            note=text,
            defer_vector_index=True,
        )
    return ingest_document_text(
        session,
        text,
        user_id=user_id,
        telegram_chat_id=conversation_key,
        source_type="text",
        defer_vector_index=True,
    )


def _undo_latest(
    session: Session,
    *,
    user_id: str,
    conversation_key: str,
    hooks: ActionHooks | None = None,
) -> tuple[str, dict]:
    hooks = hooks or _default_hooks()
    entry = _latest_entry(session, user_id=user_id, conversation_key=conversation_key)
    if not entry:
        return "Nothing to undo for this conversation.", {}
    memory_ids = [memory.id for memory in entry.memories]
    preview = maybe_decrypt_text(entry.raw_text)[:180]
    entry_id = entry.id
    delete_voice_assets_for_entry(session, user_id=user_id, raw_entry_id=entry.id)
    session.delete(entry)
    session.commit()
    hooks.refresh_vectors(memory_ids, [], entry_id)
    return f"Undid latest saved item {entry_id[:10]}.\nPreview: {preview}", {"entry_id": entry_id}


def _mark_latest_as_chat(
    session: Session,
    *,
    user_id: str,
    conversation_key: str,
    hooks: ActionHooks | None = None,
) -> tuple[str, dict]:
    hooks = hooks or _default_hooks()
    entry = (
        session.query(RawEntry)
        .filter(
            RawEntry.user_id == user_id,
            RawEntry.telegram_chat_id == conversation_key,
            RawEntry.processed_status != CHAT_STATUS,
        )
        .order_by(RawEntry.created_at_utc.desc(), RawEntry.id.desc())
        .first()
    )
    if not entry:
        return "I could not find a recent journal save to mark as chat.", {}
    entry_id = entry.id
    preview = maybe_decrypt_text(entry.raw_text)[:180]
    memory_ids, restored = demote_entry_to_chat(session, entry, user_id=user_id)
    session.commit()
    hooks.refresh_vectors(memory_ids, restored, entry_id)
    restored_note = f" Restored {len(restored)} older memory record(s)." if restored else ""
    return (
        f"Marked the latest saved entry as chat memory, not journal memory.\nPreview: {preview}{restored_note}",
        {"entry_id": entry_id, "restored_memories": len(restored)},
    )


def _latest_entry(session: Session, *, user_id: str, conversation_key: str) -> RawEntry | None:
    query = session.query(RawEntry).filter(RawEntry.user_id == user_id)
    if conversation_key:
        query = query.filter(RawEntry.telegram_chat_id == conversation_key)
    return query.order_by(RawEntry.created_at_utc.desc(), RawEntry.id.desc()).first()


def _latest_chat_entry(session: Session, *, user_id: str, conversation_key: str) -> RawEntry | None:
    return (
        session.query(RawEntry)
        .filter(
            RawEntry.user_id == user_id,
            RawEntry.telegram_chat_id == conversation_key,
            RawEntry.processed_status == CHAT_STATUS,
        )
        .order_by(RawEntry.created_at_utc.desc(), RawEntry.id.desc())
        .first()
    )


def _format_recent_entries(session: Session, *, user_id: str, limit: int = 5) -> str:
    entries = (
        session.query(RawEntry)
        .filter(RawEntry.user_id == user_id, RawEntry.is_private == False)
        .order_by(RawEntry.created_at_utc.desc())
        .limit(limit)
        .all()
    )
    if not entries:
        return "No recent entries yet."
    lines = ["Recent entries:"]
    for entry in entries:
        lines.append(f"- [{entry.local_date} {entry.local_time}] {maybe_decrypt_text(entry.raw_text)[:180]}")
    return "\n".join(lines)


def _format_today_entries(session: Session, *, user_id: str) -> str:
    today = local_today()
    entries = (
        session.query(RawEntry)
        .filter(RawEntry.user_id == user_id, RawEntry.local_date == today, RawEntry.is_private == False)
        .order_by(RawEntry.created_at_utc.desc())
        .limit(10)
        .all()
    )
    if not entries:
        return "No entries saved today yet."
    lines = [f"Today's entries ({today}):"]
    for entry in entries:
        lines.append(f"- [{entry.local_time}] {maybe_decrypt_text(entry.raw_text)[:180]}")
    return "\n".join(lines)


def _format_search_results(session: Session, query: str, *, user_id: str) -> str:
    if not query:
        return "Tell me what to search for."
    results = search(query, session=session, user_id=user_id, limit=5)
    if not results:
        return f"No memory results found for: {query}"
    lines = [f"Top memory results for: {query}"]
    for result in results:
        lines.append(f"- [{result.local_date or 'undated'}] {result.text[:240]}")
    return "\n".join(lines)


def _format_context_diagnostics_reply(
    session: Session,
    query: str,
    *,
    user_id: str,
    conversation_key: str,
    hooks: ActionHooks | None = None,
) -> str:
    hooks = hooks or _default_hooks()
    if not query:
        return "Tell me what memory question to diagnose."
    info = hooks.describe_context(
        query,
        session,
        chat_id=conversation_key,
        include_private=False,
        user_id=user_id,
    )
    return _trim_text(hooks.format_context(info), 6000)


def _format_source_detail(session: Session, ref: str, *, user_id: str) -> str:
    if not ref:
        return "Tell me which saved source to inspect."
    from thoughtpins.library import find_document

    doc = find_document(session, user_id, ref)
    if not doc:
        return f"No saved source found for '{ref}'."
    lines = [
        f"Source: {doc.title}",
        f"Type: {doc.source_type}",
        f"Status: {doc.status}",
    ]
    original_url = doc.canonical_url or doc.source_url or doc.original_url
    if original_url:
        lines.append(f"Original: {original_url}")
    if doc.status != "processed":
        lines.append("Full text is not available yet. Add article text you can access for complete recall.")
    if doc.summary:
        lines.extend(["", "Summary:", doc.summary[:1000]])
    chunks = sorted(doc.chunks, key=lambda chunk: chunk.chunk_index)
    if chunks:
        lines.extend(["", "First excerpts:"])
        for chunk in chunks[:3]:
            lines.append(f"- [{chunk.chunk_index + 1}] {chunk.text[:350]}")
    return _trim_text("\n".join(lines), 6000)


def _format_library(session: Session, *, user_id: str) -> str:
    docs = list_documents(session, user_id, limit=8)
    if not docs:
        return "No saved sources yet."
    lines = ["Saved sources:"]
    for doc in docs:
        original_url = doc.canonical_url or doc.source_url or doc.original_url
        suffix = f" - {original_url}" if original_url else ""
        lines.append(f"- {doc.title} ({doc.status}, {len(doc.chunks)} memory sections){suffix}")
    return "\n".join(lines)


def _format_doctor_reply(session: Session, *, user_id: str, conversation_key: str) -> tuple[str, bool]:
    from thoughtpins.founder.ops import build_doctor_report

    report, ok = build_doctor_report(session, user_id=user_id, chat_id=conversation_key)
    return _trim_text(report, 6000), ok


def _format_audit_reply(session: Session, *, user_id: str) -> str:
    from thoughtpins.memory.audit import audit_memory_system, format_audit_report

    report = audit_memory_system(session, user_id=user_id)
    return _trim_text(format_audit_report(report), 6000)


def _format_document_reply(result) -> str:
    if result.status == "needs_text":
        return (
            f"Saved source link: {result.title}\n"
            "The article was not publicly readable and no authorized open copy was available. "
            "I can still remember its title, link, and any notes you add."
        )
    status = "Duplicate source" if result.duplicate else "Saved source"
    return (
        f"{status}: {result.title}\n"
        f"{result.chunks} searchable {'section is' if result.chunks == 1 else 'sections are'} now available in your reading memory."
    )


def _classification_meta(decision: ChatRouteDecision) -> dict:
    classification = dict(decision.classification or {})
    meta = {
        "classification": classification,
        "natural_action": decision.natural_route.action if decision.natural_route else None,
    }
    hint = _routing_hint(decision.route_type, classification)
    if hint:
        meta["routing_hint"] = hint
    return meta


def _routing_hint(route_type: str, classification: dict) -> str | None:
    confidence = _safe_float(classification.get("confidence"))
    classified_type = str(classification.get("type") or route_type)
    if route_type == "ambiguous" or classified_type == "ambiguous":
        return "Replying as chat. Say `save that` to turn this into a journal entry, or `journal:` next time."
    if route_type == "journal_entry" and confidence is not None and confidence < 0.75:
        return "Saved as journal. Say `that was just chat` if this should stay conversational."
    if route_type in {"document_link", "document_text"}:
        return "Saved as library source. Journal memories still take priority in conversation."
    return None


def _safe_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _strip_route_prefix(text: str, msg_type: str) -> str:
    stripped = text.strip()
    lowered = stripped.lower()
    prefixes: tuple[str, ...] = ()
    if msg_type == "journal_entry":
        prefixes = ("save:", "journal:", "log:", "note to self:")
    elif msg_type == "conversation":
        prefixes = ("chat:", "just chat:", "talk:")
    elif msg_type in {"document_link", "document_text"}:
        prefixes = ("read:", "article:", "source:", "doc:", "document:")
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return stripped[len(prefix) :].strip()
    return stripped


def _extract_urls(text: str) -> list[str]:
    pattern = re.compile(r"https?://[^\s<>\]\)\"']+", re.IGNORECASE)
    seen: set[str] = set()
    urls: list[str] = []
    for match in pattern.finditer(text):
        url = match.group(0).rstrip(".,;:")
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _trim_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 80)].rstrip() + "\n\n[trimmed]"
