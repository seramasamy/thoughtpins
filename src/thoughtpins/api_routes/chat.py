"""Memory-backed chat and question-answering routes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger

from thoughtpins.api_contracts import (
    AskResponse,
    ChatConversationResponse,
    ChatConversationsPageResponse,
    ChatMessageResponse,
    ChatMessagesPageResponse,
    ChatRequest,
    ChatResponse,
)
from thoughtpins.api_contracts.common import INTERNAL_ERROR_MESSAGE
from thoughtpins.api_preferences import resolve_private_context_preference
from thoughtpins.audit import record_audit_event
from thoughtpins.chat.store import find_conversation, list_conversations, list_messages
from thoughtpins.db import ChatConversation, ChatMessage
from thoughtpins.jobs import IngestionDispatchUnavailable
from thoughtpins.pagination import decode_cursor, encode_cursor
from thoughtpins.store import get_session


def create_chat_router(
    *,
    current_user_dependency: Callable[..., str],
    answer_with_llm_fn: Callable[..., str],
    build_memory_context_fn: Callable[..., str],
    execute_chat_message_fn: Callable[..., Any],
) -> APIRouter:
    router = APIRouter()

    @router.get("/ask", response_model=AskResponse)
    @router.get("/v1/ask", response_model=AskResponse)
    async def ask(
        q: str = Query(..., min_length=1, max_length=2_000, description="Question about the journal"),
        user_id: str = Depends(current_user_dependency),
    ) -> AskResponse:
        session = get_session()
        try:
            include_private = resolve_private_context_preference(session, user_id=user_id, requested=None)
            query = q.strip()
            context = build_memory_context_fn(query, session, user_id=user_id, include_private=include_private)
            answer = answer_with_llm_fn(query, session, user_id=user_id, include_private=include_private)
            return AskResponse(query=query, answer=answer, context_size_chars=len(context))
        except IngestionDispatchUnavailable as exc:
            raise HTTPException(
                status_code=503,
                detail="Memory processing is temporarily unavailable. Retry the same message.",
            ) from exc
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Ask failed")
            raise HTTPException(status_code=500, detail=INTERNAL_ERROR_MESSAGE) from exc
        finally:
            session.close()

    @router.post("/v1/chat", response_model=ChatResponse)
    async def chat(
        payload: ChatRequest,
        user_id: str = Depends(current_user_dependency),
    ) -> ChatResponse:
        session = get_session()
        try:
            include_private = resolve_private_context_preference(
                session,
                user_id=user_id,
                requested=payload.include_private,
            )
            result = execute_chat_message_fn(
                session,
                payload.text,
                user_id=user_id,
                surface=payload.surface,
                conversation_id=payload.conversation_id,
                message_id=payload.message_id,
                author_user_id=user_id,
                include_private=include_private,
                confirm_action=payload.confirm_action,
                pending_action_id=payload.pending_action_id,
            )
            record_audit_event(
                session,
                user_id=user_id,
                action=f"chat.{result.route_type}",
                metadata={
                    "status": result.status,
                    "route_type": result.route_type,
                    "entry_id": result.entry_id,
                    "job_id": result.job_id,
                    "document_id": result.document_id,
                    "requires_confirmation": result.requires_confirmation,
                    "surface": payload.surface,
                    "private_context_included": include_private,
                },
            )
            return ChatResponse(
                status=result.status,
                route_type=result.route_type,
                reply=result.reply,
                entry_id=result.entry_id,
                job_id=result.job_id,
                document_id=result.document_id,
                requires_confirmation=result.requires_confirmation,
                confirmation_prompt=result.confirmation_prompt,
                context_size_chars=result.context_size_chars,
                metadata=result.metadata,
            )
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Chat failed")
            raise HTTPException(status_code=500, detail=INTERNAL_ERROR_MESSAGE) from exc
        finally:
            session.close()

    @router.get("/v1/chat/conversations", response_model=ChatConversationsPageResponse)
    async def get_conversations(
        page: int = Query(1, ge=1),
        limit: int = Query(50, ge=1, le=100),
        surface: str | None = Query(None, max_length=32, pattern=r"^[A-Za-z0-9_-]+$"),
        cursor: str | None = Query(None, max_length=1024),
        user_id: str = Depends(current_user_dependency),
    ) -> ChatConversationsPageResponse:
        session = get_session()
        try:
            position = _decode_cursor(cursor, sort="chat.conversations.updated", direction="desc") if cursor else None
            items, total, has_next = list_conversations(
                session,
                user_id=user_id,
                page=page,
                limit=limit,
                surface=surface,
                cursor=position,
            )
            return ChatConversationsPageResponse(
                items=[_conversation_response(item) for item in items],
                page=page,
                limit=limit,
                total=total,
                has_next=has_next,
                next_cursor=_chat_cursor(
                    items,
                    has_next=has_next,
                    sort="chat.conversations.updated",
                    direction="desc",
                    timestamp_attr="updated_at_utc",
                ),
            )
        finally:
            session.close()

    @router.get("/v1/chat/conversations/{conversation_id}/messages", response_model=ChatMessagesPageResponse)
    async def get_conversation_messages(
        conversation_id: str,
        page: int = Query(1, ge=1),
        limit: int = Query(100, ge=1, le=200),
        cursor: str | None = Query(None, max_length=1024),
        user_id: str = Depends(current_user_dependency),
    ) -> ChatMessagesPageResponse:
        session = get_session()
        try:
            conversation = find_conversation(session, user_id=user_id, conversation_id=conversation_id)
            if not conversation:
                raise HTTPException(status_code=404, detail="Chat conversation not found")
            position = _decode_cursor(cursor, sort="chat.messages.created", direction="asc") if cursor else None
            items, total, has_next = list_messages(
                session,
                user_id=user_id,
                conversation_id=conversation.id,
                page=page,
                limit=limit,
                cursor=position,
            )
            return ChatMessagesPageResponse(
                items=[_message_response(item) for item in items],
                page=page,
                limit=limit,
                total=total,
                has_next=has_next,
                next_cursor=_chat_cursor(
                    items,
                    has_next=has_next,
                    sort="chat.messages.created",
                    direction="asc",
                    timestamp_attr="created_at_utc",
                ),
            )
        finally:
            session.close()

    return router


def _conversation_response(conversation: ChatConversation) -> ChatConversationResponse:
    return ChatConversationResponse(
        id=conversation.id,
        conversation_key=conversation.conversation_key,
        surface=conversation.surface,
        title=conversation.title,
        created_at_utc=conversation.created_at_utc.isoformat() if conversation.created_at_utc else None,
        updated_at_utc=conversation.updated_at_utc.isoformat() if conversation.updated_at_utc else None,
        last_message_at_utc=conversation.last_message_at_utc.isoformat() if conversation.last_message_at_utc else None,
    )


def _message_response(message: ChatMessage) -> ChatMessageResponse:
    return ChatMessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        role=message.role,
        text=message.text,
        route_type=message.route_type,
        status=message.status,
        entry_id=message.raw_entry_id,
        job_id=message.job_id,
        document_id=message.document_id,
        created_at_utc=message.created_at_utc.isoformat() if message.created_at_utc else None,
        metadata=dict(message.metadata_json or {}),
    )


def _decode_cursor(value: str, *, sort: str, direction: str):
    try:
        return decode_cursor(value, sort=sort, direction=direction)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _chat_cursor(
    rows: list[ChatConversation] | list[ChatMessage],
    *,
    has_next: bool,
    sort: str,
    direction: str,
    timestamp_attr: str,
) -> str | None:
    if not has_next or not rows:
        return None
    last = rows[-1]
    occurred_at = getattr(last, timestamp_attr)
    if occurred_at is None:
        return None
    return encode_cursor(
        sort=sort,
        direction=direction,
        occurred_at=occurred_at,
        row_id=last.id,
    )
