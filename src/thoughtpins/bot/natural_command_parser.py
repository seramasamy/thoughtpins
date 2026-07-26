"""Decision layer for conservative natural command routing."""

from __future__ import annotations

from thoughtpins.bot.natural_command_patterns import (
    _extract_backup_list_args,
    _extract_confidential_on_args,
    _extract_context_query,
    _extract_delete_search_query,
    _extract_export_args,
    _extract_forget_args,
    _extract_importance_prompt_setting,
    _extract_importance_value,
    _extract_merge_args,
    _extract_rename_args,
    _extract_report_args,
    _extract_search_query,
    _extract_source_ref,
    _is_audit_request,
    _is_backup_create_request,
    _is_confidential_off_request,
    _is_confidential_status_request,
    _is_doctor_request,
    _is_library_request,
    _is_mark_previous_chat_request,
    _is_memory_summary_request,
    _is_recent_request,
    _is_reindex_request,
    _is_save_last_chat_request,
    _is_status_request,
    _is_today_request,
    _is_undo_importance_request,
    _is_undo_request,
    _normalize,
    _starts_like_journal_note,
)
from thoughtpins.bot.natural_command_types import NaturalCommandRoute


def route_natural_command(text: str) -> NaturalCommandRoute | None:
    """Return a command route for clear operational requests, else None."""
    original = text.strip()
    if not original:
        return None
    lowered = _normalize(original)

    if _starts_like_journal_note(lowered):
        return None

    safe = _route_safe(lowered, original)
    if safe:
        return safe

    risky = _route_risky(lowered, original)
    if risky:
        return risky

    return None


def _route_safe(lowered: str, original: str) -> NaturalCommandRoute | None:
    if lowered in {"help", "show help", "commands", "command list", "what can you do"}:
        return NaturalCommandRoute("help")
    if lowered in {"how do i use this", "what commands do you have", "show commands"}:
        return NaturalCommandRoute("help")

    if _is_doctor_request(lowered):
        return NaturalCommandRoute("doctor")
    if _is_audit_request(lowered):
        return NaturalCommandRoute("audit")
    if _is_status_request(lowered):
        return NaturalCommandRoute("status")

    if _is_today_request(lowered):
        return NaturalCommandRoute("today")
    if _is_recent_request(lowered):
        return NaturalCommandRoute("recent")

    if _is_memory_summary_request(lowered):
        return NaturalCommandRoute("memory")

    search_query = _extract_search_query(lowered, original)
    if search_query:
        return NaturalCommandRoute("search", [search_query])

    context_query = _extract_context_query(lowered, original)
    if context_query:
        return NaturalCommandRoute("context_why", ["why", *context_query.split()])

    source_ref = _extract_source_ref(lowered, original)
    if source_ref:
        return NaturalCommandRoute("source", source_ref.split())

    if _is_library_request(lowered):
        return NaturalCommandRoute("library")

    report_args = _extract_report_args(lowered, original)
    if report_args:
        return NaturalCommandRoute("report", report_args)

    backup_list_args = _extract_backup_list_args(lowered)
    if backup_list_args:
        return NaturalCommandRoute("backup", backup_list_args)

    if _is_confidential_status_request(lowered):
        return NaturalCommandRoute("confidential")
    if _is_confidential_off_request(lowered):
        return NaturalCommandRoute("confidential", ["off"])
    importance_prompt_setting = _extract_importance_prompt_setting(lowered)
    if importance_prompt_setting is not None:
        return NaturalCommandRoute("importance_prompts", ["on" if importance_prompt_setting else "off"])
    if _is_undo_importance_request(lowered):
        return NaturalCommandRoute("undo_importance")
    importance = _extract_importance_value(lowered)
    if importance is not None:
        return NaturalCommandRoute("set_importance", [importance])
    if _is_mark_previous_chat_request(lowered):
        return NaturalCommandRoute(
            "mark_chat",
            reason="User said the previous save should be treated as chat, not journal.",
        )
    if _is_save_last_chat_request(lowered):
        return NaturalCommandRoute(
            "save_last_chat",
            reason="User asked to promote the latest chat turn into journal memory.",
        )

    delete_query = _extract_delete_search_query(lowered, original)
    if delete_query:
        return NaturalCommandRoute(
            "candidate_delete_search",
            [delete_query],
            reason="Destructive deletion needs an exact memory id.",
        )

    return None


def _route_risky(lowered: str, original: str) -> NaturalCommandRoute | None:
    if _is_undo_request(lowered):
        return NaturalCommandRoute(
            "undo",
            needs_confirmation=True,
            prompt=(
                "This will delete the most recent Telegram-saved item for this chat. "
                "Reply `confirm undo` to proceed, or `cancel`."
            ),
        )

    forget_args = _extract_forget_args(lowered, original)
    if forget_args:
        return NaturalCommandRoute(
            "forget",
            forget_args,
            needs_confirmation=True,
            prompt=("This will remove a saved memory/entity. Reply `confirm forget` to proceed, or `cancel`."),
        )

    rename_args = _extract_rename_args(original)
    if rename_args:
        return NaturalCommandRoute(
            "rename",
            rename_args,
            needs_confirmation=True,
            prompt=(
                "This will rename an entity and keep the old name as an alias. "
                "Reply `confirm rename` to proceed, or `cancel`."
            ),
        )

    merge_args = _extract_merge_args(original)
    if merge_args:
        return NaturalCommandRoute(
            "merge",
            merge_args,
            needs_confirmation=True,
            prompt=(
                "This will merge two entities and rewrite references. Reply `confirm merge` to proceed, or `cancel`."
            ),
        )

    if _is_backup_create_request(lowered):
        return NaturalCommandRoute(
            "backup",
            needs_confirmation=True,
            prompt=("This will create a local backup archive. Reply `confirm backup` to proceed, or `cancel`."),
        )

    export_args = _extract_export_args(lowered)
    if export_args is not None:
        return NaturalCommandRoute(
            "export",
            export_args,
            needs_confirmation=True,
            prompt=("This will export journal data to a file. Reply `confirm export` to proceed, or `cancel`."),
        )

    if _is_reindex_request(lowered):
        return NaturalCommandRoute(
            "reindex",
            needs_confirmation=True,
            prompt=("This will rebuild the search index. Reply `confirm reindex` to proceed, or `cancel`."),
        )

    confidential_args = _extract_confidential_on_args(lowered)
    if confidential_args:
        return NaturalCommandRoute(
            "confidential",
            confidential_args,
            needs_confirmation=True,
            prompt=(
                "This starts confidential mode unlock for private entries. "
                "Reply `confirm confidential` to proceed, or `cancel`."
            ),
        )

    return None
