"""Durable chat storage helpers shared by web, mobile, and bot surfaces."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from thoughtpins.chat.natural_commands import PENDING_TTL_SECONDS, NaturalCommandRoute
from thoughtpins.db import ChatConversation, ChatMessage, PendingChatAction
from thoughtpins.pagination import CursorPosition
from thoughtpins.utils import utcnow

PROMPT_HISTORY_LIMIT = 200


def get_or_create_conversation(
    session: Session,
    *,
    user_id: str,
    conversation_key: str,
    surface: str,
    title_hint: str = "",
) -> ChatConversation:
    conversation = (
        session.query(ChatConversation)
        .filter(
            ChatConversation.user_id == user_id,
            ChatConversation.conversation_key == conversation_key,
        )
        .first()
    )
    if conversation:
        return conversation

    now = utcnow()
    conversation = ChatConversation(
        user_id=user_id,
        conversation_key=conversation_key,
        surface=(surface or "api")[:32],
        title=_title_from_text(title_hint),
        created_at_utc=now,
        updated_at_utc=now,
        last_message_at_utc=None,
        metadata_json={},
    )
    session.add(conversation)
    session.flush()
    return conversation


def append_chat_message(
    session: Session,
    conversation: ChatConversation,
    *,
    user_id: str,
    role: str,
    text: str,
    route_type: str | None = None,
    status: str | None = None,
    raw_entry_id: str | None = None,
    job_id: str | None = None,
    document_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ChatMessage:
    now = utcnow()
    cleaned = (text or "").strip()
    message = ChatMessage(
        user_id=user_id,
        conversation_id=conversation.id,
        role=role,
        text=cleaned,
        route_type=route_type,
        status=status,
        raw_entry_id=raw_entry_id,
        job_id=job_id,
        document_id=document_id,
        created_at_utc=now,
        metadata_json=dict(metadata or {}),
    )
    conversation.updated_at_utc = now
    conversation.last_message_at_utc = now
    if role == "user" and cleaned and not conversation.title:
        conversation.title = _title_from_text(cleaned)
    session.add(message)
    session.flush()
    return message


def prompt_history(
    session: Session,
    *,
    user_id: str,
    conversation_id: str,
    limit: int = PROMPT_HISTORY_LIMIT,
) -> list[dict[str, str]]:
    rows = (
        session.query(ChatMessage)
        .filter(
            ChatMessage.user_id == user_id,
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.role.in_(("user", "assistant")),
            ChatMessage.superseded_at_utc.is_(None),
        )
        .order_by(ChatMessage.created_at_utc.desc(), ChatMessage.id.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    return [{"role": str(row.role), "content": str(row.text)} for row in rows if row.text]


def supersede_from(
    session: Session,
    *,
    user_id: str,
    conversation_id: str,
    message_id: str,
) -> tuple[list[ChatMessage], list[str]]:
    """Retire an edited turn and everything the conversation built on it.

    Editing a message invalidates the replies that followed it, the same way it
    does in any chat product. What differs here is that a retired turn may have
    written durable memory — a journal entry, a saved source — and a chat edit
    is not consent to delete what someone wrote. So rows are marked rather than
    removed, and the ids of any entries the retired turns created are returned
    for the caller to surface. Silently orphaning them, or silently destroying
    them, are both worse than saying so.

    Returns the retired messages and the raw entry ids still standing behind
    them. Returns empty when the target is not this user's own live user turn
    in this conversation, so a bad id is a no-op rather than an error.
    """
    target = (
        session.query(ChatMessage)
        .filter(
            ChatMessage.id == message_id,
            ChatMessage.user_id == user_id,
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.role == "user",
            ChatMessage.superseded_at_utc.is_(None),
        )
        .first()
    )
    if target is None:
        return [], []

    doomed = (
        session.query(ChatMessage)
        .filter(
            ChatMessage.user_id == user_id,
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.superseded_at_utc.is_(None),
            or_(
                ChatMessage.created_at_utc > target.created_at_utc,
                and_(ChatMessage.created_at_utc == target.created_at_utc, ChatMessage.id >= target.id),
            ),
        )
        .order_by(ChatMessage.created_at_utc.asc(), ChatMessage.id.asc())
        .all()
    )
    retired_at = datetime.now(UTC).replace(tzinfo=None)
    for row in doomed:
        row.superseded_at_utc = retired_at
    orphaned = [str(row.raw_entry_id) for row in doomed if row.raw_entry_id]
    return doomed, orphaned


def attribute_supersede(messages: list[ChatMessage], *, replacement_id: str) -> None:
    """Point retired turns at the message that replaced them."""
    for row in messages:
        row.superseded_by_message_id = replacement_id


def latest_live_user_message_id(session: Session, *, user_id: str, conversation_id: str) -> str | None:
    """The id of this user's most recent live turn in a conversation.

    Read back rather than threaded out of the engine: the engine has several
    return paths that each append the turn, and widening its result type across
    all of them to carry one identifier is more coupling than the identifier is
    worth. This is one lookup on an index the conversation loader already uses.
    """
    row = (
        session.query(ChatMessage.id)
        .filter(
            ChatMessage.user_id == user_id,
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.role == "user",
            ChatMessage.superseded_at_utc.is_(None),
        )
        .order_by(ChatMessage.created_at_utc.desc(), ChatMessage.id.desc())
        .first()
    )
    return str(row[0]) if row else None


def list_conversations(
    session: Session,
    *,
    user_id: str,
    page: int,
    limit: int,
    surface: str | None = None,
    cursor: CursorPosition | None = None,
) -> tuple[list[ChatConversation], int, bool]:
    query = session.query(ChatConversation).filter(ChatConversation.user_id == user_id)
    if surface:
        query = query.filter(ChatConversation.surface == surface)
    total = query.count()
    if cursor:
        query = query.filter(
            or_(
                ChatConversation.updated_at_utc < cursor.occurred_at,
                and_(
                    ChatConversation.updated_at_utc == cursor.occurred_at,
                    ChatConversation.id < cursor.row_id,
                ),
            )
        )
    query = query.order_by(ChatConversation.updated_at_utc.desc(), ChatConversation.id.desc())
    if not cursor:
        query = query.offset((page - 1) * limit)
    rows = query.limit(limit + 1).all()
    return rows[:limit], total, len(rows) > limit


def list_messages(
    session: Session,
    *,
    user_id: str,
    conversation_id: str,
    page: int,
    limit: int,
    cursor: CursorPosition | None = None,
) -> tuple[list[ChatMessage], int, bool]:
    query = session.query(ChatMessage).filter(
        ChatMessage.user_id == user_id,
        ChatMessage.conversation_id == conversation_id,
        # An edited turn stays on the row for provenance but leaves the
        # transcript, so a replayed conversation matches what the user sees.
        ChatMessage.superseded_at_utc.is_(None),
    )
    total = query.count()
    if cursor:
        query = query.filter(
            or_(
                ChatMessage.created_at_utc > cursor.occurred_at,
                and_(ChatMessage.created_at_utc == cursor.occurred_at, ChatMessage.id > cursor.row_id),
            )
        )
    query = query.order_by(ChatMessage.created_at_utc.asc(), ChatMessage.id.asc())
    if not cursor:
        query = query.offset((page - 1) * limit)
    rows = query.limit(limit + 1).all()
    return rows[:limit], total, len(rows) > limit


def find_conversation(session: Session, *, user_id: str, conversation_id: str) -> ChatConversation | None:
    return (
        session.query(ChatConversation)
        .filter(ChatConversation.user_id == user_id, ChatConversation.id == conversation_id)
        .first()
    )


def create_pending_action(
    session: Session,
    conversation: ChatConversation,
    *,
    user_id: str,
    route: NaturalCommandRoute,
    prompt: str,
    metadata: dict[str, Any] | None = None,
) -> PendingChatAction:
    expire_stale_pending_actions(session, user_id=user_id, conversation_id=conversation.id)
    now = utcnow()
    pending = PendingChatAction(
        user_id=user_id,
        conversation_id=conversation.id,
        action=route.action,
        args_json=list(route.args),
        prompt=prompt,
        status="pending",
        created_at_utc=now,
        expires_at_utc=now + timedelta(seconds=PENDING_TTL_SECONDS),
        metadata_json=dict(metadata or {}),
    )
    session.add(pending)
    session.flush()
    return pending


def latest_pending_action(
    session: Session,
    *,
    user_id: str,
    conversation_id: str,
) -> PendingChatAction | None:
    expire_stale_pending_actions(session, user_id=user_id, conversation_id=conversation_id)
    return (
        session.query(PendingChatAction)
        .filter(
            PendingChatAction.user_id == user_id,
            PendingChatAction.conversation_id == conversation_id,
            PendingChatAction.status == "pending",
            PendingChatAction.expires_at_utc >= utcnow(),
        )
        .order_by(PendingChatAction.created_at_utc.desc(), PendingChatAction.id.desc())
        .first()
    )


def get_pending_action(
    session: Session,
    *,
    user_id: str,
    pending_action_id: str,
) -> PendingChatAction | None:
    expire_stale_pending_actions(session, user_id=user_id)
    return (
        session.query(PendingChatAction)
        .filter(
            PendingChatAction.user_id == user_id,
            PendingChatAction.id == pending_action_id,
            PendingChatAction.status == "pending",
            PendingChatAction.expires_at_utc >= utcnow(),
        )
        .first()
    )


def resolve_pending_action(pending: PendingChatAction, status: str) -> None:
    pending.status = status
    pending.resolved_at_utc = utcnow()


def expire_stale_pending_actions(
    session: Session,
    *,
    user_id: str,
    conversation_id: str | None = None,
) -> int:
    query = session.query(PendingChatAction).filter(
        PendingChatAction.user_id == user_id,
        PendingChatAction.status == "pending",
        PendingChatAction.expires_at_utc < utcnow(),
    )
    if conversation_id:
        query = query.filter(PendingChatAction.conversation_id == conversation_id)
    stale = query.all()
    for pending in stale:
        pending.status = "expired"
        pending.resolved_at_utc = utcnow()
    return len(stale)


def _title_from_text(text: str) -> str:
    cleaned = " ".join((text or "").strip().split())
    if not cleaned:
        return ""
    if len(cleaned) <= 80:
        return cleaned
    return cleaned[:77].rstrip() + "..."
