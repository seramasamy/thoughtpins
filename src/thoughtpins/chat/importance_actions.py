"""Natural-language commands for user-controlled memory importance."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from thoughtpins.chat.models import ChatEngineResult
from thoughtpins.importance import (
    importance_label,
    normalize_user_importance,
    set_importance_prompts_enabled,
    set_latest_importance,
    undo_latest_importance,
)


def execute_importance_action(
    action: str,
    session: Session,
    *,
    args: list[str],
    user_id: str,
    conversation_key: str,
    classification_metadata: dict[str, Any],
) -> ChatEngineResult | None:
    """Execute an importance command, or return ``None`` for another action domain."""

    if action == "set_importance":
        return _set_importance(
            session,
            args=args,
            user_id=user_id,
            conversation_key=conversation_key,
            classification_metadata=classification_metadata,
        )
    if action == "undo_importance":
        return _undo_importance(
            session,
            user_id=user_id,
            conversation_key=conversation_key,
            classification_metadata=classification_metadata,
        )
    if action == "importance_prompts":
        return _set_prompt_preference(
            session,
            args=args,
            user_id=user_id,
            classification_metadata=classification_metadata,
        )
    return None


def _set_importance(
    session: Session,
    *,
    args: list[str],
    user_id: str,
    conversation_key: str,
    classification_metadata: dict[str, Any],
) -> ChatEngineResult:
    value = normalize_user_importance(args[0] if args else None)
    updated = set_latest_importance(
        session,
        user_id=user_id,
        value=value,
        conversation_key=conversation_key,
    )
    metadata: dict[str, Any]
    if not updated:
        reply = "I could not find a recent saved entry to rate."
        metadata = {"importance_found": False}
    elif not updated.changed:
        reply = f"That entry is already rated {importance_label(updated.user_importance)}."
        metadata = {
            "importance_found": True,
            "importance_changed": False,
            "user_importance": updated.user_importance,
            "target_type": updated.target_type,
            "target_id": updated.target_id,
        }
    elif value is None:
        reply = "Cleared the importance rating from your latest saved entry."
        metadata = {
            "importance_found": True,
            "importance_changed": True,
            "user_importance": None,
            "target_type": updated.target_type,
            "target_id": updated.target_id,
        }
    else:
        reply = f"Rated your latest saved entry {importance_label(value)}."
        metadata = {
            "importance_found": True,
            "importance_changed": True,
            "user_importance": value,
            "target_type": updated.target_type,
            "target_id": updated.target_id,
        }
    return ChatEngineResult(
        status="importance_updated" if updated and updated.changed else "replied",
        route_type="natural_command",
        reply=reply,
        entry_id=updated.entry_id if updated else None,
        metadata=classification_metadata | metadata,
    )


def _undo_importance(
    session: Session,
    *,
    user_id: str,
    conversation_key: str,
    classification_metadata: dict[str, Any],
) -> ChatEngineResult:
    updated = undo_latest_importance(
        session,
        user_id=user_id,
        conversation_key=conversation_key,
    )
    metadata: dict[str, Any]
    if not updated:
        reply = "There is no recent importance change to undo."
        metadata = {"importance_undo_found": False}
    else:
        reply = f"Restored the previous importance: {importance_label(updated.user_importance)}."
        metadata = {
            "importance_undo_found": True,
            "user_importance": updated.user_importance,
            "target_type": updated.target_type,
            "target_id": updated.target_id,
        }
    return ChatEngineResult(
        status="importance_undone" if updated else "replied",
        route_type="natural_command",
        reply=reply,
        entry_id=updated.entry_id if updated else None,
        metadata=classification_metadata | metadata,
    )


def _set_prompt_preference(
    session: Session,
    *,
    args: list[str],
    user_id: str,
    classification_metadata: dict[str, Any],
) -> ChatEngineResult:
    enabled = bool(args and args[0].lower() == "on")
    changed = set_importance_prompts_enabled(session, user_id=user_id, enabled=enabled)
    reply = (
        "I will occasionally offer an importance rating after substantial journal saves."
        if enabled and changed
        else "Importance prompts are off. You can still rate any entry whenever you want."
    )
    return ChatEngineResult(
        status="preferences_updated" if changed else "replied",
        route_type="natural_command",
        reply=reply,
        metadata=classification_metadata | {"importance_prompts_enabled": enabled},
    )
