"""Unified chat routing and execution for product clients."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from thoughtpins.chat.actions import (
    ActionHooks,
    _classification_meta,
    _clean_text,
    _format_document_reply,
    _ingest_document,
    _strip_route_prefix,
)
from thoughtpins.chat.actions import (
    _execute_natural_route as _execute_natural_route_action,
)
from thoughtpins.chat.actions import (
    _save_journal_turn as _save_journal_turn_action,
)
from thoughtpins.chat.conversation_state import CONVERSATION_CACHE, HISTORY_MAX_MESSAGES
from thoughtpins.chat.memory_answer import answer_with_llm
from thoughtpins.chat.models import ChatEngineResult, ChatRouteDecision
from thoughtpins.chat.natural_commands import (
    NaturalCommandRoute,
    interpret_confirmation,
    route_natural_command,
)
from thoughtpins.chat.reply import generate_conversation_reply
from thoughtpins.chat.store import (
    append_chat_message,
    get_or_create_conversation,
    get_pending_action,
    latest_pending_action,
    prompt_history,
    resolve_pending_action,
)
from thoughtpins.db import ChatConversation, PendingChatAction
from thoughtpins.ingestion.classify import classify_message
from thoughtpins.ingestion.pipeline import process_message
from thoughtpins.memory.context_package import (
    _format_context_diagnostics,
    build_memory_context_package,
    describe_memory_context_package,
)
from thoughtpins.memory.corrections import store_and_apply_correction
from thoughtpins.memory.vector_refresh import refresh_vectors_after_removed_memories
from thoughtpins.users import lock_active_user_for_write

CHAT_API_SOURCE = "api_chat"
MAX_CHAT_TEXT_CHARS = 50_000


def _action_hooks() -> ActionHooks:
    """Bind compatibility seams at request time, without global mutation."""
    return ActionHooks(
        process_message=process_message,
        refresh_vectors=refresh_vectors_after_removed_memories,
        describe_context=describe_memory_context_package,
        format_context=_format_context_diagnostics,
    )


def _execute_natural_route(*args, **kwargs) -> ChatEngineResult:
    kwargs.setdefault("hooks", _action_hooks())
    return _execute_natural_route_action(*args, **kwargs)


def _save_journal_turn(*args, **kwargs) -> ChatEngineResult:
    kwargs.setdefault("hooks", _action_hooks())
    return _save_journal_turn_action(*args, **kwargs)


def conversation_key(*, surface: str, conversation_id: str | None = None) -> str:
    """Return a compact stable key used for chat history and undo scoping."""
    surface = re.sub(r"[^a-zA-Z0-9_-]+", "-", (surface or "api").strip()).strip("-").lower() or "api"
    conversation_id = (
        re.sub(
            r"[^a-zA-Z0-9_.:-]+",
            "-",
            (conversation_id or "default").strip(),
        ).strip("-")
        or "default"
    )
    key = f"{surface}:{conversation_id}"
    if len(key) <= 64:
        return key
    from thoughtpins.utils import hash_text

    return f"{surface}:{hash_text(key)}"


def route_chat_message(text: str) -> ChatRouteDecision:
    """Classify one natural chat message without executing side effects."""
    cleaned = _clean_text(text)
    if not cleaned:
        raise ValueError("Text cannot be empty")
    if len(cleaned) > MAX_CHAT_TEXT_CHARS:
        raise ValueError("Message is too long to process in one chat turn")

    natural_route = route_natural_command(cleaned)
    if natural_route:
        return ChatRouteDecision(
            route_type="natural_command",
            routed_text=cleaned,
            natural_route=natural_route,
            classification={
                "type": "natural_command",
                "intent": natural_route.action,
                "confidence": 0.98,
            },
        )

    classification = classify_message(cleaned)
    msg_type = str(classification.get("type") or "journal_entry")
    return ChatRouteDecision(
        route_type=msg_type,
        routed_text=_strip_route_prefix(cleaned, msg_type),
        classification=classification,
    )


def execute_chat_message(
    session: Session,
    text: str,
    *,
    user_id: str,
    surface: str = "api",
    conversation_id: str | None = None,
    message_id: str = "",
    author_user_id: str = "",
    include_private: bool = False,
    confirm_action: bool = False,
    pending_action_id: str | None = None,
) -> ChatEngineResult:
    """Execute one natural message as chat, journal, document, or operation."""
    lock_active_user_for_write(session, user_id)
    key = conversation_key(surface=surface, conversation_id=conversation_id)
    source = f"{surface[:20]}_chat" if surface else CHAT_API_SOURCE
    if source == "api_chat":
        source = CHAT_API_SOURCE

    cleaned_text = _clean_text(text)
    if not cleaned_text:
        raise ValueError("Text cannot be empty")

    conversation = get_or_create_conversation(
        session,
        user_id=user_id,
        conversation_key=key,
        surface=surface,
        title_hint=cleaned_text,
    )
    durable_history = prompt_history(session, user_id=user_id, conversation_id=conversation.id)

    pending_result = _maybe_execute_pending_action(
        session,
        cleaned_text,
        user_id=user_id,
        conversation=conversation,
        conversation_key=key,
        source=source[:32],
        pending_action_id=pending_action_id,
        confirm_action=confirm_action,
    )
    if pending_result:
        append_chat_message(
            session,
            conversation,
            user_id=user_id,
            role="user",
            text=cleaned_text,
            route_type="natural_command",
            status=pending_result.status,
            metadata={"pending_action_id": pending_action_id},
        )
        return _finalize_chat_result(session, conversation=conversation, user_id=user_id, result=pending_result)

    decision = route_chat_message(cleaned_text)
    append_chat_message(
        session,
        conversation,
        user_id=user_id,
        role="user",
        text=cleaned_text,
        route_type=decision.route_type,
        status="received",
        metadata=_classification_meta(decision),
    )

    if decision.natural_route:
        result = _execute_natural_route(
            session,
            decision.natural_route,
            decision=decision,
            user_id=user_id,
            conversation=conversation,
            conversation_key=key,
            source=source[:32],
            confirm_action=confirm_action,
        )
        return _finalize_chat_result(session, conversation=conversation, user_id=user_id, result=result)

    msg_type = decision.route_type
    routed_text = decision.routed_text

    if msg_type == "command":
        result = ChatEngineResult(
            status="command_hint",
            route_type="command",
            reply="You can just say what you want naturally. Manual slash commands are optional.",
            metadata=_classification_meta(decision),
        )
        return _finalize_chat_result(session, conversation=conversation, user_id=user_id, result=result)

    if msg_type in {"conversation", "query", "ambiguous"}:
        _seed_prompt_history(key, durable_history)
        reply = generate_conversation_reply(
            routed_text,
            chat_id=key,
            user_id=user_id,
            session=session,
            include_private=include_private,
            telegram_message_id=message_id,
            author_user_id=author_user_id or user_id,
            chat_source=source[:32],
        )
        ctx = build_memory_context_package(
            routed_text, session, chat_id=key, user_id=user_id, include_private=include_private
        )
        result = ChatEngineResult(
            status="replied",
            route_type="chat",
            reply=reply,
            context_size_chars=len(ctx),
            metadata=_classification_meta(decision),
        )
        return _finalize_chat_result(session, conversation=conversation, user_id=user_id, result=result)

    if msg_type == "report_request":
        ctx = build_memory_context_package(
            routed_text, session, chat_id=key, user_id=user_id, include_private=include_private
        )
        reply = answer_with_llm(routed_text, session, include_private=include_private, user_id=user_id)
        result = ChatEngineResult(
            status="replied",
            route_type="report_request",
            reply=reply,
            context_size_chars=len(ctx),
            metadata=_classification_meta(decision),
        )
        return _finalize_chat_result(session, conversation=conversation, user_id=user_id, result=result)

    if msg_type in {"document_link", "document_text"}:
        result = _ingest_document(session, routed_text, user_id=user_id, conversation_key=key, msg_type=msg_type)
        chat_result = ChatEngineResult(
            status="document_saved",
            route_type=msg_type,
            reply=_format_document_reply(result),
            entry_id=result.raw_entry_id,
            document_id=result.document_id,
            metadata=_classification_meta(decision)
            | {
                "title": result.title,
                "chunks": result.chunks,
                "memories": result.memories,
                "duplicate": result.duplicate,
            },
        )
        return _finalize_chat_result(session, conversation=conversation, user_id=user_id, result=chat_result)

    if msg_type == "correction":
        correction_result = store_and_apply_correction(
            session,
            routed_text,
            user_id=user_id,
            source=source[:32],
            telegram_message_id=message_id,
            telegram_chat_id=key,
            author_user_id=author_user_id or user_id,
        )
        if correction_result.fixes:
            reply = "Correction applied.\n" + "\n".join(f"- {fix}" for fix in correction_result.fixes)
        else:
            reply = "Correction saved."
        chat_result = ChatEngineResult(
            status="correction_saved",
            route_type="correction",
            reply=reply,
            metadata=_classification_meta(decision) | {"fixes": list(correction_result.fixes)},
        )
        return _finalize_chat_result(session, conversation=conversation, user_id=user_id, result=chat_result)

    if msg_type == "mixed":
        stored = _save_journal_turn(
            session,
            routed_text,
            user_id=user_id,
            source=source[:32],
            conversation_key=key,
            message_id=message_id,
            author_user_id=author_user_id or user_id,
        )
        _seed_prompt_history(key, durable_history)
        reply = generate_conversation_reply(
            routed_text,
            chat_id=key,
            user_id=user_id,
            session=session,
            include_private=include_private,
            telegram_message_id=message_id,
            author_user_id=author_user_id or user_id,
            chat_source=source[:32],
        )
        result = ChatEngineResult(
            status=stored.status,
            route_type="mixed",
            reply=reply,
            entry_id=stored.entry_id,
            job_id=stored.job_id,
            metadata=_classification_meta(decision) | stored.metadata,
        )
        return _finalize_chat_result(session, conversation=conversation, user_id=user_id, result=result)

    stored = _save_journal_turn(
        session,
        routed_text,
        user_id=user_id,
        source=source[:32],
        conversation_key=key,
        message_id=message_id,
        author_user_id=author_user_id or user_id,
    )
    result = ChatEngineResult(
        status=stored.status,
        route_type="journal_entry",
        reply=stored.reply,
        entry_id=stored.entry_id,
        job_id=stored.job_id,
        metadata=_classification_meta(decision) | stored.metadata,
    )
    return _finalize_chat_result(session, conversation=conversation, user_id=user_id, result=result)


def _maybe_execute_pending_action(
    session: Session,
    text: str,
    *,
    user_id: str,
    conversation: ChatConversation,
    conversation_key: str,
    source: str,
    pending_action_id: str | None,
    confirm_action: bool,
) -> ChatEngineResult | None:
    pending: PendingChatAction | None = None
    if pending_action_id:
        pending = get_pending_action(session, user_id=user_id, pending_action_id=pending_action_id)
        if not pending or pending.conversation_id != conversation.id:
            return ChatEngineResult(
                status="confirmation_expired",
                route_type="natural_command",
                reply="That pending action is no longer available. Try the request again.",
                metadata={"pending_action_id": pending_action_id},
            )
    else:
        pending = latest_pending_action(session, user_id=user_id, conversation_id=conversation.id)

    if not pending:
        return None

    pending_route = NaturalCommandRoute(
        action=pending.action,
        args=[str(arg) for arg in pending.args_json or []],
        needs_confirmation=True,
        prompt=pending.prompt,
    )
    intent = "confirm" if confirm_action else interpret_confirmation(text, pending_route)
    if not intent:
        return None

    if intent == "cancel":
        resolve_pending_action(pending, "canceled")
        action_name = pending.action.replace("_", " ")
        return ChatEngineResult(
            status="canceled",
            route_type="natural_command",
            reply=f"Canceled {action_name}.",
            metadata={"pending_action_id": pending.id, "action": pending.action},
        )

    confirmed_route = NaturalCommandRoute(
        action=pending.action,
        args=[str(arg) for arg in pending.args_json or []],
        needs_confirmation=False,
        prompt=pending.prompt,
    )
    decision = ChatRouteDecision(
        route_type="natural_command",
        routed_text=text,
        classification={"type": "natural_command", "intent": pending.action, "confidence": 1.0},
        natural_route=confirmed_route,
    )
    resolve_pending_action(pending, "confirmed")
    return _execute_natural_route(
        session,
        confirmed_route,
        decision=decision,
        user_id=user_id,
        conversation=conversation,
        conversation_key=conversation_key,
        source=source,
        confirm_action=True,
        pending_action_id=pending.id,
    )


def _finalize_chat_result(
    session: Session,
    *,
    conversation: ChatConversation,
    user_id: str,
    result: ChatEngineResult,
) -> ChatEngineResult:
    result.metadata = dict(result.metadata or {})
    result.metadata.setdefault("conversation_db_id", conversation.id)
    result.metadata.setdefault("conversation_key", conversation.conversation_key)
    append_chat_message(
        session,
        conversation,
        user_id=user_id,
        role="assistant",
        text=result.reply,
        route_type=result.route_type,
        status=result.status,
        raw_entry_id=result.entry_id,
        job_id=result.job_id,
        document_id=result.document_id,
        metadata=result.metadata,
    )
    lock_active_user_for_write(session, user_id)
    session.commit()
    return result


def _seed_prompt_history(chat_id: str, history: list[dict[str, str]]) -> None:
    CONVERSATION_CACHE[chat_id] = list(history[-HISTORY_MAX_MESSAGES:])
