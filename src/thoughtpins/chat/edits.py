"""Publish a replacement branch only once its response has been produced."""

from __future__ import annotations

from sqlalchemy.orm import Session

from thoughtpins.chat.store import attribute_supersede, branch_from
from thoughtpins.db import ChatConversation, ChatMessage
from thoughtpins.users import lock_active_user_for_write
from thoughtpins.utils import utcnow


def prepare_edited_branch(
    session: Session,
    *,
    user_id: str,
    conversation_id: str,
    message_id: str | None,
) -> list[ChatMessage]:
    if not message_id:
        return []
    rows = branch_from(session, user_id=user_id, conversation_id=conversation_id, message_id=message_id)
    if not rows:
        raise ValueError("That message is no longer editable in this conversation.")
    return rows


def hold_replacement(message: ChatMessage, branch: list[ChatMessage]) -> None:
    # Some ingestion actions commit their durable memory before replying. Keep
    # an unfinished replacement out of history even across those commits. A
    # failed edit leaves the original visible, and its draft can be retried.
    if branch:
        message.superseded_at_utc = utcnow()


def finalize_edited_branch(
    session: Session,
    *,
    user_id: str,
    branch: list[ChatMessage],
    replacement_id: str,
) -> dict:
    if not branch:
        return {}
    lock_active_user_for_write(session, user_id)
    # Serialize publication of competing edits even if their ingestion actions
    # committed earlier. A shared user lock coordinates deletion, not edits.
    session.query(ChatConversation).filter(
        ChatConversation.id == branch[0].conversation_id,
        ChatConversation.user_id == user_id,
    ).with_for_update().one()
    for row in branch:
        session.refresh(row)
        if row.user_id != user_id or row.superseded_at_utc is not None:
            raise ValueError("This conversation changed while editing. Refresh and try again.")
    replacement = (
        session.query(ChatMessage)
        .filter(
            ChatMessage.id == replacement_id,
            ChatMessage.user_id == user_id,
            ChatMessage.conversation_id == branch[0].conversation_id,
        )
        .one()
    )
    replacement.superseded_at_utc = None
    retired_at = utcnow()
    for row in branch:
        row.superseded_at_utc = retired_at
    attribute_supersede(branch, replacement_id=replacement_id)
    # The engine commits retirement and the completed replacement together.
    return {
        "superseded_message_ids": [str(row.id) for row in branch],
        "orphaned_entry_ids": sorted({str(row.raw_entry_id) for row in branch if row.raw_entry_id}),
    }
