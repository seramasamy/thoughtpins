"""Pattern recognizers for conservative natural command routing."""

from __future__ import annotations

import re

from thoughtpins.chat.natural_command_types import JOURNAL_PREFIX_BLOCKLIST


def _normalize(text: str) -> str:
    text = text.strip().lower()
    text = text.replace("'", "'").replace("'", "'")
    text = text.replace("?", "").replace("!", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _strip_polite(text: str) -> str:
    text = text.strip()
    for prefix in ("please ", "pls ", "can you ", "could you ", "would you "):
        if text.startswith(prefix):
            return text[len(prefix) :].strip()
    return text


def _extract_importance_value(lowered: str) -> str | None:
    """Parse only explicit commands so ordinary five-star prose stays journal text."""
    text = _strip_polite(lowered)
    clear_forms = {
        "clear that rating",
        "clear the rating",
        "clear its importance",
        "remove that rating",
        "remove the importance rating",
        "unrate that",
        "unrate the last entry",
    }
    if text in clear_forms:
        return "clear"

    if text in {
        "mark that important",
        "mark the last entry important",
        "that was really important",
        "that was very important",
    }:
        return "5"
    if text in {
        "mark that low importance",
        "that was not important",
        "that wasn't important",
        "the last entry was not important",
    }:
        return "1"

    words = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5"}
    match = re.fullmatch(
        r"(?:rate|give|set|mark)\s+"
        r"(?:(?:my|the)\s+)?(?:(?:last|latest)\s+)?(?:(?:entry|journal|note|memory|save)\s+)?"
        r"(?:that\s+|this\s+)?(?:as\s+|to\s+)?"
        r"([1-5]|one|two|three|four|five)(?:\s*(?:out of 5|stars?))?",
        text,
    )
    if not match:
        match = re.fullmatch(
            r"(?:rate|give)\s+(?:that|this|it)\s+([1-5]|one|two|three|four|five)\s*(?:out of 5|stars?)?",
            text,
        )
    if not match:
        match = re.fullmatch(
            r"(?:set|mark)\s+(?:(?:my|the)\s+)?(?:(?:last|latest)\s+)?"
            r"(?:entry|journal|note|memory|save)(?:'s)?\s+(?:importance|rating)\s+"
            r"(?:as\s+|to\s+)?([1-5]|one|two|three|four|five)(?:\s*(?:out of 5|stars?))?",
            text,
        )
    if not match:
        return None
    value = match.group(1)
    return words.get(value, value)


def _is_undo_importance_request(lowered: str) -> bool:
    text = _strip_polite(lowered)
    return text in {
        "undo importance",
        "undo that importance",
        "undo that importance change",
        "undo that rating",
        "undo the rating",
        "revert that rating",
        "revert the importance",
    }


def _extract_importance_prompt_setting(lowered: str) -> bool | None:
    text = _strip_polite(lowered)
    if text in {
        "ask me to rate important entries",
        "ask me to rate journal entries",
        "occasionally ask me to rate entries",
        "turn on importance prompts",
    }:
        return True
    if text in {
        "stop asking me to rate entries",
        "do not ask me to rate entries",
        "don't ask me to rate entries",
        "turn off importance prompts",
    }:
        return False
    return None


def _starts_like_journal_note(lowered: str) -> bool:
    candidate = _strip_polite(lowered)
    return any(candidate.startswith(prefix) for prefix in JOURNAL_PREFIX_BLOCKLIST)


def _is_status_request(lowered: str) -> bool:
    text = _strip_polite(lowered)
    exact = {
        "status",
        "system status",
        "bot status",
        "are you running",
        "are you working",
        "is everything running",
        "is everything working",
        "everything running",
        "everything working",
    }
    return text in exact or bool(
        re.fullmatch(r"(is )?(the )?(bot|system|telegram|everything) (up|online|alive|running|working)", text)
    )


def _is_doctor_request(lowered: str) -> bool:
    text = _strip_polite(lowered)
    phrases = (
        "run health check",
        "run a health check",
        "health check",
        "run diagnostics",
        "diagnostics",
        "doctor",
        "system doctor",
        "check system health",
        "check bot health",
    )
    return text in phrases


def _is_audit_request(lowered: str) -> bool:
    text = _strip_polite(lowered)
    phrases = (
        "audit memory",
        "audit my memory",
        "audit memory system",
        "audit my memory system",
        "memory audit",
        "run memory audit",
        "run a memory audit",
        "check memory quality",
        "check retrieval quality",
    )
    return text in phrases


def _is_today_request(lowered: str) -> bool:
    text = _strip_polite(lowered)
    patterns = (
        r"(show me )?(today|today's|todays) (notes|entries|journal|summary)",
        r"what did i (write|save|log) today",
        r"(show|list) (my )?(notes|entries) from today",
    )
    return any(re.fullmatch(pattern, text) for pattern in patterns)


def _is_recent_request(lowered: str) -> bool:
    text = _strip_polite(lowered)
    patterns = (
        r"(show me )?recent (notes|entries|journal|memories)",
        r"(show|list) (my )?(recent|latest|last) (notes|entries|journal|memories)",
        r"what did i (write|save|log) recently",
        r"what have i (written|saved|logged) recently",
        r"last (ten|10) (notes|entries)",
    )
    return text in {"recent", "recent entries", "recent notes"} or any(
        re.fullmatch(pattern, text) for pattern in patterns
    )


def _is_memory_summary_request(lowered: str) -> bool:
    text = _strip_polite(lowered)
    return text in {
        "memory",
        "memory status",
        "memory summary",
        "show memory",
        "show memory status",
        "show memory summary",
        "show memories",
        "memory health",
    }


def _extract_search_query(lowered: str, original: str) -> str | None:
    lower_text = _strip_polite(lowered)
    original_text = _strip_polite(original.strip())
    patterns = (
        r"search(?: my)? (?:memory|memories|journal|entries|notes)(?: for)? (.+)",
        r"search for (.+) in (?:my )?(?:memory|memories|journal|entries|notes)",
        r"find (?:memories|entries|notes) (?:about|for|on) (.+)",
        r"look up (?:memories|entries|notes) (?:about|for|on) (.+)",
        r"show me (?:memories|entries|notes) (?:about|for|on) (.+)",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, lower_text)
        if match:
            return _same_suffix(original_text, lower_text, match.group(1))
    return None


def _extract_context_query(lowered: str, original: str) -> str | None:
    lower_text = _strip_polite(lowered)
    original_text = _strip_polite(original.strip())
    patterns = (
        r"(?:debug|diagnose|show) context (?:for|on) (.+)",
        r"why (?:did you|would you) use (?:that )?context (?:for|on) (.+)",
        r"show context diagnostics (?:for|on) (.+)",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, lower_text)
        if match:
            return _same_suffix(original_text, lower_text, match.group(1))
    return None


def _extract_source_ref(lowered: str, original: str) -> str | None:
    lower_text = _strip_polite(lowered)
    original_text = _strip_polite(original.strip())
    if lower_text.startswith(("source:", "read:", "article:", "doc:", "document:")):
        return None
    patterns = (
        r"(?:show|open|inspect) source (.+)",
        r"(?:show|open|inspect) saved source (.+)",
        r"what(?:'s| is) in source (.+)",
        r"source (.+)",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, lower_text)
        if match:
            return _same_suffix(original_text, lower_text, match.group(1))
    return None


def _is_library_request(lowered: str) -> bool:
    text = _strip_polite(lowered)
    return text in {
        "library",
        "show library",
        "show saved articles",
        "show saved documents",
        "show saved sources",
        "list saved articles",
        "list saved documents",
        "list saved sources",
        "reading memory",
        "show reading memory",
    }


def _extract_report_args(lowered: str, original: str) -> list[str] | None:
    text = _strip_polite(lowered)
    original_text = _strip_polite(original.strip())
    simple = {
        "weekly report": ["weekly"],
        "monthly report": ["monthly"],
        "daily report": ["daily"],
        "make weekly report": ["weekly"],
        "generate weekly report": ["weekly"],
        "create weekly report": ["weekly"],
    }
    if text in simple:
        return simple[text]
    match = re.fullmatch(r"(?:make|generate|create) report (?:about|on|for) (.+)", text)
    if match:
        return _same_suffix(original_text, text, match.group(1)).split()
    return None


def _extract_backup_list_args(lowered: str) -> list[str] | None:
    text = _strip_polite(lowered)
    if text in {"list backups", "show backups", "show backup list", "backup list"}:
        return ["list"]
    return None


def _is_confidential_status_request(lowered: str) -> bool:
    text = _strip_polite(lowered)
    return text in {"confidential", "confidential status", "private mode status"}


def _is_confidential_off_request(lowered: str) -> bool:
    text = _strip_polite(lowered)
    return text in {
        "turn off confidential mode",
        "disable confidential mode",
        "confidential off",
        "private mode off",
    }


def _extract_delete_search_query(lowered: str, original: str) -> str | None:
    lower_text = _strip_polite(lowered)
    original_text = _strip_polite(original.strip())
    patterns = (
        r"(?:delete|forget|remove) (?:the )?(?:memory|memories|entry|entries) about (.+)",
        r"(?:delete|forget|remove) anything about (.+)",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, lower_text)
        if match:
            target = match.group(1).strip()
            if _looks_like_memory_ref(target):
                return None
            return _same_suffix(original_text, lower_text, target)
    return None


def _is_undo_request(lowered: str) -> bool:
    text = _strip_polite(lowered)
    return text in {
        "undo",
        "undo that",
        "undo the last thing",
        "undo last save",
        "undo last entry",
        "undo latest entry",
        "delete that",
        "delete the last thing",
        "dont save that",
        "don't save that",
        "do not save that",
        "remove that",
        "remove the last thing",
        "delete last save",
        "delete last entry",
        "remove last save",
        "remove latest entry",
    }


def _is_mark_previous_chat_request(lowered: str) -> bool:
    text = _strip_polite(lowered)
    return text in {
        "that was just chat",
        "that was chat",
        "that wasnt a journal entry",
        "that wasn't a journal entry",
        "that was not a journal entry",
        "mark that as chat",
        "mark the last one as chat",
        "mark last entry as chat",
        "treat that as chat",
        "treat that as conversation",
        "dont treat that as journal",
        "don't treat that as journal",
        "do not treat that as journal",
        "dont make that a memory",
        "don't make that a memory",
        "do not make that a memory",
    }


def _is_save_last_chat_request(lowered: str) -> bool:
    text = _strip_polite(lowered)
    return text in {
        "save that",
        "save that as journal",
        "save that as a journal entry",
        "actually save that",
        "actually save that as journal",
        "make that a journal entry",
        "turn that into a journal entry",
        "remember that as a journal entry",
    }


def _extract_forget_args(lowered: str, original: str) -> list[str] | None:
    lower_text = _strip_polite(lowered)
    original_text = _strip_polite(original.strip())
    patterns = (
        r"(?:forget|delete|remove) memory (?:id )?([a-z0-9_-]{6,})",
        r"(?:forget|delete|remove) entity (.+)",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, lower_text)
        if not match:
            continue
        value = _same_suffix(original_text, lower_text, match.group(1)).strip()
        if "entity" in pattern:
            return ["entity", value]
        return ["memory", value]
    return None


def _extract_rename_args(original: str) -> list[str] | None:
    text = _strip_polite(original.strip())
    match = re.fullmatch(
        r"(?i)(?:rename|rename entity|change entity name)\s+(.+?)\s+(?:to|->|=>)\s+(.+)",
        text,
    )
    if not match:
        return None
    old = match.group(1).strip().strip("'\"")
    new = match.group(2).strip().strip("'\"")
    if not old or not new:
        return None
    return [old, "->", new]


def _extract_merge_args(original: str) -> list[str] | None:
    text = _strip_polite(original.strip())
    match = re.fullmatch(r"(?i)merge\s+(.+?)\s+into\s+(.+)", text)
    if not match:
        return None
    duplicate = match.group(1).strip().strip("'\"")
    keep = match.group(2).strip().strip("'\"")
    if not duplicate or not keep:
        return None
    return [_quote_arg(keep), _quote_arg(duplicate)]


def _is_backup_create_request(lowered: str) -> bool:
    text = _strip_polite(lowered)
    return text in {
        "backup",
        "create backup",
        "make backup",
        "backup my journal",
        "backup my data",
        "backup everything",
        "run backup",
    }


def _extract_export_args(lowered: str) -> list[str] | None:
    text = _strip_polite(lowered)
    data_phrases = {
        "export data",
        "export my data",
        "export account data",
        "export json",
        "export journal data",
    }
    vault_phrases = {
        "export",
        "export journal",
        "export vault",
        "export obsidian",
        "export obsidian vault",
    }
    if text in data_phrases:
        return ["data"]
    if text in vault_phrases:
        return []
    return None


def _is_reindex_request(lowered: str) -> bool:
    text = _strip_polite(lowered)
    return text in {
        "reindex",
        "rebuild index",
        "rebuild the index",
        "rebuild memory index",
        "rebuild the memory index",
        "rebuild search index",
        "rebuild the search index",
        "reindex memory",
        "reindex memories",
        "refresh search index",
    }


def _extract_confidential_on_args(lowered: str) -> list[str] | None:
    text = _strip_polite(lowered)
    if text in {
        "turn on confidential mode",
        "enable confidential mode",
        "confidential on",
        "private mode on",
        "include private entries",
        "include private memories",
    }:
        return ["on"]
    return None


def _same_suffix(original: str, lowered: str, lowered_suffix: str) -> str:
    """Recover original casing for a suffix captured from the normalized string."""
    suffix = lowered_suffix.strip()
    if not suffix:
        return ""
    index = lowered.rfind(suffix)
    if index == -1:
        return suffix
    return original[index:].strip().strip("?.!")


def _looks_like_memory_ref(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9_-]{6,}", value.strip()))


def _quote_arg(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    return f'"{value}"'
