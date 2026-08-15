"""Query-aware assembly and diagnostics for bounded memory context packages."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from thoughtpins.chat.context_budget import truncate_middle as _truncate_middle
from thoughtpins.chat.message_memory import is_chat_memory_entry
from thoughtpins.chat.vault_context import (
    VAULT_FILE_CONTEXT_MAX_CHARS as _VAULT_FILE_CONTEXT_MAX_CHARS,
)
from thoughtpins.chat.vault_context import (
    build_vault_file_context,
)
from thoughtpins.config import config
from thoughtpins.crypto import maybe_decrypt_text
from thoughtpins.db import ActionItem, Entity, Expense, Memory, RawEntry
from thoughtpins.memory.context_scope import scope_user as _scope_user
from thoughtpins.memory.evidence_plan import build_response_evidence_plan
from thoughtpins.memory.full_context import (
    build_full_context,
    build_full_context_within,
    build_navigational_map,
)
from thoughtpins.memory.query_terms import context_tokens as _context_tokens
from thoughtpins.memory.search import search
from thoughtpins.memory.search_types import SearchResult


def _format_memory_context_line(memory: Memory) -> str:
    subj = memory.subject_entity.canonical_name if memory.subject_entity else ""
    obj = memory.object_entity.canonical_name if memory.object_entity else ""
    parts = [f"[{memory.local_date}] [{memory.memory_type}] id={memory.id[:10]}"]
    if subj:
        parts.append(f"subject={subj}")
    if memory.predicate:
        parts.append(f"predicate={memory.predicate}")
    if obj:
        parts.append(f"object={obj}")
    if memory.source_provenance:
        parts.append(f"source={memory.source_provenance[:80]}")
    if memory.supersedes_memory_id:
        parts.append(f"supersedes={memory.supersedes_memory_id[:10]}")
    parts.append(f"sensitivity={memory.sensitivity}")
    parts.append(f"confidence={memory.confidence}")
    if memory.raw_entry and memory.raw_entry.user_importance is not None:
        parts.append(f"user_importance={memory.raw_entry.user_importance}/5")
    return " ".join(parts) + f"\n  {memory.text}"


def _memory_query(session, include_private: bool, user_id: str | None):
    query = _scope_user(session.query(Memory), Memory, user_id).filter(Memory.valid_to.is_(None))
    if not include_private:
        query = query.join(RawEntry).filter(RawEntry.is_private == False)
    return query


def _raw_entry_query(session, include_private: bool, user_id: str | None):
    query = _scope_user(session.query(RawEntry), RawEntry, user_id)
    if not include_private:
        query = query.filter(RawEntry.is_private == False)
    return query


def _rank_memories_for_query(memories: list[Memory], query: str) -> list[Memory]:
    tokens = _context_tokens(query)
    if not tokens:
        return []

    scored: list[tuple[float, Memory]] = []
    for memory in memories:
        haystack_parts = [
            memory.text or "",
            memory.memory_type or "",
            memory.predicate or "",
        ]
        if memory.subject_entity:
            haystack_parts.append(memory.subject_entity.canonical_name)
        if memory.object_entity:
            haystack_parts.append(memory.object_entity.canonical_name)
        haystack = " ".join(haystack_parts).lower()
        score = sum(1.0 for token in tokens if token in haystack)
        if score <= 0:
            continue
        if memory.local_date:
            score += 0.01
        if memory.raw_entry and memory.raw_entry.user_importance is not None:
            from thoughtpins.importance import importance_bonus

            score += importance_bonus(memory.raw_entry.user_importance)
        scored.append((score, memory))

    return [
        memory
        for _, memory in sorted(
            scored,
            key=lambda pair: (pair[0], pair[1].local_date or date.min, pair[1].created_at_utc),
            reverse=True,
        )
    ]


def _dedupe_memories(memories: list[Memory], limit: int) -> list[Memory]:
    selected: list[Memory] = []
    seen: set[str] = set()
    for memory in memories:
        if memory.id in seen:
            continue
        seen.add(memory.id)
        selected.append(memory)
        if len(selected) >= limit:
            break
    return selected


def _format_raw_entry(entry: RawEntry) -> str:
    prefix = "[PRIVATE] " if entry.is_private else ""
    source_label = "chat" if is_chat_memory_entry(entry) else (entry.source or "journal")
    importance = f" [importance={entry.user_importance}/5]" if entry.user_importance is not None else ""
    return (
        f"- [{entry.local_date} {entry.local_time}] [{source_label}]{importance} "
        f"{prefix}{maybe_decrypt_text(entry.raw_text)}"
    )


def _append_context_section(
    sections: list[tuple[str, str]],
    title: str,
    content: str,
) -> None:
    content = (content or "").strip()
    if content:
        sections.append((title, content))


def _render_context_sections(sections: list[tuple[str, str]], max_chars: int) -> str:
    rendered: list[str] = []
    used = 0
    for title, content in sections:
        block_overhead = len(title) + 10
        remaining = max_chars - used - block_overhead
        if remaining <= 0:
            break
        block_content = _truncate_middle(content, remaining)
        block = f"## {title}\n{block_content}".strip()
        rendered.append(block)
        used += len(block) + 2
    return "\n\n".join(rendered)


def build_full_memory_context_package(
    session,
    *,
    query: str = "",
    include_private: bool = False,
    user_id: str | None = None,
    max_chars: int | None = None,
    include_vault: bool = True,
) -> str:
    """Build the old exhaustive long-context package."""
    max_chars = max_chars or config.MEMORY_CONTEXT_MAX_CHARS
    sections: list[tuple[str, str]] = []
    _append_context_section(
        sections,
        "CONTEXT RULES",
        "Use this context as private memory, not as a message to quote verbatim. "
        "If a fact is not in this context, say you do not know yet. Do not reveal "
        "private entries unless confidential mode is enabled.",
    )
    _append_context_section(
        sections,
        "NAVIGATIONAL MEMORY MAP",
        build_navigational_map(session, include_private=include_private, user_id=user_id),
    )
    if query.strip():
        ranked_evidence = search(
            query,
            session=session,
            user_id=user_id,
            include_private=include_private,
            limit=max(config.MEMORY_CONTEXT_RELEVANT_MEMORIES * 2, 40),
        )
        _append_context_section(
            sections,
            "QUERY-CONDITIONED RESPONSE EVIDENCE PLAN",
            build_response_evidence_plan(query, ranked_evidence).render(),
        )
    _append_context_section(
        sections,
        "FULL STRUCTURED JOURNAL DATABASE",
        build_full_context(session, include_private=include_private, user_id=user_id),
    )
    if include_vault:
        _append_context_section(sections, "EXPORTED VAULT FILE TEXT", build_vault_file_context(user_id))
    return _render_context_sections(sections, max_chars)


def _smart_context_header(
    nav_map: str,
    *,
    chat_id: str,
    include_private: bool,
) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    _append_context_section(
        sections,
        "CONTEXT RULES",
        "Smart context mode is active. Use the navigational map as the index. "
        "Use exact memories and raw excerpts below for details. Bring up relevant "
        "past facts naturally when they help the current reply. If the answer needs "
        "older exact text that is not included, say what is missing instead of guessing. "
        "If correction memories conflict with old raw text, the correction memory wins.",
    )
    if chat_id:
        _append_context_section(
            sections,
            "CURRENT TELEGRAM CHAT",
            f"chat_id={chat_id}\nconfidential_mode={include_private}\ncontext_mode=smart",
        )
    _append_context_section(sections, "NAVIGATIONAL MEMORY MAP", nav_map)
    return sections


@dataclass(frozen=True)
class _SmartMemorySelection:
    relevant: tuple[Memory, ...]
    selected: tuple[Memory, ...]
    graph_evidence: tuple[SearchResult, ...]


def _select_smart_memories(
    query: str,
    search_results: list[SearchResult],
    session,
    *,
    include_private: bool,
    user_id: str | None,
) -> _SmartMemorySelection:
    recent_memories = (
        _memory_query(session, include_private, user_id)
        .order_by(Memory.local_date.desc(), Memory.created_at_utc.desc())
        .limit(max(config.MEMORY_CONTEXT_RECENT_MEMORIES, 80))
        .all()
    )
    graph_evidence = tuple(
        result
        for result in search_results
        if result.memory_id.startswith(("graph:", "source:")) or "sql_graph" in result.retrieval_sources
    )[: config.MEMORY_HYBRID_GRAPH_RESULTS]
    searched_ids = [result.memory_id for result in search_results if not result.memory_id.startswith("raw:")]
    relevant: list[Memory] = []
    if searched_ids:
        found = {
            memory.id: memory
            for memory in _memory_query(session, include_private, user_id).filter(Memory.id.in_(searched_ids)).all()
        }
        relevant = [found[memory_id] for memory_id in searched_ids if memory_id in found]
    if len(relevant) < config.MEMORY_CONTEXT_RELEVANT_MEMORIES:
        relevant = _dedupe_memories(
            relevant + _rank_memories_for_query(recent_memories, query),
            config.MEMORY_CONTEXT_RELEVANT_MEMORIES,
        )
    recent = recent_memories[: config.MEMORY_CONTEXT_RECENT_MEMORIES]
    selected = _dedupe_memories(
        relevant + recent,
        config.MEMORY_CONTEXT_RELEVANT_MEMORIES + config.MEMORY_CONTEXT_RECENT_MEMORIES,
    )
    return _SmartMemorySelection(tuple(relevant), tuple(selected), graph_evidence)


def _append_memory_evidence_sections(sections: list[tuple[str, str]], selection: _SmartMemorySelection) -> None:
    if selection.relevant:
        _append_context_section(
            sections,
            "QUERY-RELEVANT MEMORIES AND SOURCES",
            "\n".join(_format_memory_context_line(memory) for memory in selection.relevant),
        )
    if selection.selected:
        _append_context_section(
            sections,
            "RECENT AND SELECTED MEMORIES",
            "\n".join(_format_memory_context_line(memory) for memory in selection.selected),
        )
    if selection.graph_evidence:
        _append_context_section(
            sections,
            "GRAPH AND SOURCE RETRIEVAL EVIDENCE",
            "\n".join(
                f"- [{result.memory_id}] score={result.score:.2f} "
                f"via={','.join(result.retrieval_sources)}: {result.evidence_text[:900]}"
                for result in selection.graph_evidence
            ),
        )


def _append_open_actions(
    sections: list[tuple[str, str]],
    session,
    *,
    include_private: bool,
    user_id: str | None,
) -> None:
    query = _scope_user(session.query(ActionItem), ActionItem, user_id)
    if not include_private:
        query = query.join(RawEntry, ActionItem.raw_entry_id == RawEntry.id).filter(RawEntry.is_private == False)
    actions = (
        query.filter(ActionItem.status != "done")
        .order_by(ActionItem.due_at.is_(None), ActionItem.due_at, ActionItem.id)
        .limit(50)
        .all()
    )
    _append_context_section(
        sections,
        "OPEN ACTION ITEMS",
        "\n".join(
            f"- [{item.status}] due="
            f"{item.due_at.isoformat(sep=' ', timespec='minutes') if item.due_at else 'no due date'}: "
            f"{item.description}"
            for item in actions
        ),
    )


def _append_raw_entry_excerpts(
    sections: list[tuple[str, str]],
    selection: _SmartMemorySelection,
    search_results: list[SearchResult],
    session,
    *,
    include_private: bool,
    user_id: str | None,
) -> None:
    raw_ids = [memory.raw_entry_id for memory in selection.selected if memory.raw_entry_id]
    raw_ids.extend(
        result.source_entry_id
        for result in search_results
        if result.memory_id.startswith("raw:") and result.source_entry_id
    )
    entries: list[RawEntry] = []
    if raw_ids:
        entries.extend(
            _raw_entry_query(session, include_private, user_id)
            .filter(RawEntry.id.in_(raw_ids))
            .order_by(RawEntry.local_date.desc(), RawEntry.created_at_utc.desc())
            .all()
        )
    entries.extend(
        _raw_entry_query(session, include_private, user_id)
        .order_by(RawEntry.local_date.desc(), RawEntry.created_at_utc.desc())
        .limit(config.MEMORY_CONTEXT_RECENT_ENTRIES)
        .all()
    )
    deduped = list({entry.id: entry for entry in entries}.values())
    _append_context_section(
        sections,
        "RAW ENTRY EXCERPTS",
        "\n".join(_format_raw_entry(entry) for entry in deduped[: config.MEMORY_CONTEXT_RECENT_ENTRIES * 2]),
    )


def _append_recent_expenses(
    sections: list[tuple[str, str]],
    session,
    *,
    include_private: bool,
    user_id: str | None,
) -> None:
    query = _scope_user(session.query(Expense), Expense, user_id)
    if not include_private:
        query = query.join(RawEntry, Expense.raw_entry_id == RawEntry.id).filter(RawEntry.is_private == False)
    lines = []
    for expense in query.order_by(Expense.id.desc()).limit(50).all():
        merchant = "unknown"
        if expense.merchant_or_place_entity_id:
            entity = (
                _scope_user(session.query(Entity), Entity, user_id)
                .filter(Entity.id == expense.merchant_or_place_entity_id)
                .first()
            )
            if entity:
                merchant = entity.canonical_name
        lines.append(
            f"- {expense.amount} {expense.currency} at {merchant}: "
            f"{expense.reason or 'unknown reason'} [{expense.category or 'other'}]"
        )
    _append_context_section(sections, "RECENT EXPENSES", "\n".join(lines))


def _append_sliced_context(
    sections: list[tuple[str, str]],
    query: str,
    search_results: list[SearchResult],
    session,
    *,
    include_private: bool,
    user_id: str | None,
) -> None:
    selection = _select_smart_memories(
        query,
        search_results,
        session,
        include_private=include_private,
        user_id=user_id,
    )
    _append_memory_evidence_sections(sections, selection)
    _append_open_actions(sections, session, include_private=include_private, user_id=user_id)
    _append_raw_entry_excerpts(
        sections,
        selection,
        search_results,
        session,
        include_private=include_private,
        user_id=user_id,
    )
    _append_recent_expenses(sections, session, include_private=include_private, user_id=user_id)


def build_smart_memory_context_package(
    query: str,
    session,
    *,
    chat_id: str = "",
    include_private: bool = False,
    user_id: str | None = None,
    max_chars: int | None = None,
    include_vault: bool = True,
) -> str:
    """Build a query-aware context package with full-context fallback for small libraries."""
    max_chars = max_chars or config.MEMORY_CONTEXT_MAX_CHARS
    nav_map = build_navigational_map(session, include_private=include_private, user_id=user_id)
    # Only the inline branch below reads this, and the sliced branch rebuilds
    # from the search results instead. Building the whole journal to discover it
    # is too large to send meant every message paid for a scan of the entire
    # corpus and then threw the result away.
    full_context = build_full_context_within(
        session,
        include_private=include_private,
        user_id=user_id,
        max_chars=max(0, config.MEMORY_CONTEXT_FULL_INLINE_MAX_CHARS),
    )
    sections = _smart_context_header(
        nav_map,
        chat_id=chat_id,
        include_private=include_private,
    )
    search_results = search(
        query,
        session=session,
        user_id=user_id,
        include_private=include_private,
        limit=max(config.MEMORY_CONTEXT_RELEVANT_MEMORIES * 2, 40),
    )
    _append_context_section(
        sections,
        "QUERY-CONDITIONED RESPONSE EVIDENCE PLAN",
        build_response_evidence_plan(query, search_results).render(),
    )
    if full_context is not None:
        _append_context_section(sections, "FULL STRUCTURED JOURNAL DATABASE", full_context)
    else:
        _append_sliced_context(
            sections,
            query,
            search_results,
            session,
            include_private=include_private,
            user_id=user_id,
        )

    if include_vault:
        vault_context = build_vault_file_context(
            user_id,
            max_chars=min(_VAULT_FILE_CONTEXT_MAX_CHARS, max_chars // 4),
        )
        _append_context_section(sections, "EXPORTED VAULT FILE TEXT", vault_context)

    return _render_context_sections(sections, max_chars)


def build_memory_context_package(
    query: str,
    session,
    *,
    chat_id: str = "",
    include_private: bool = False,
    user_id: str | None = None,
    max_chars: int | None = None,
    force_full: bool = False,
    include_vault: bool = True,
) -> str:
    """Build the active memory context package for a chat or question."""
    mode = config.MEMORY_CONTEXT_MODE
    if force_full or mode == "full":
        return build_full_memory_context_package(
            session,
            query=query,
            include_private=include_private,
            user_id=user_id,
            max_chars=max_chars,
            include_vault=include_vault,
        )
    return build_smart_memory_context_package(
        query,
        session,
        chat_id=chat_id,
        include_private=include_private,
        user_id=user_id,
        max_chars=max_chars,
        include_vault=include_vault,
    )


def _context_section_stats(context_text: str) -> list[dict[str, int | str]]:
    """Return heading-level sizes without returning private memory content."""
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", context_text, flags=re.MULTILINE))
    sections: list[dict[str, int | str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(context_text)
        title = match.group(1).strip()
        sections.append({"title": title, "chars": max(0, end - start)})
    return sections


def describe_memory_context_package(
    query: str,
    session,
    *,
    chat_id: str = "",
    include_private: bool = False,
    user_id: str | None = None,
    force_full: bool = False,
) -> dict:
    """Build diagnostics for the active context package without exposing its contents."""
    max_chars = config.MEMORY_CONTEXT_MAX_CHARS
    context_text = build_memory_context_package(
        query,
        session,
        chat_id=chat_id,
        include_private=include_private,
        user_id=user_id,
        max_chars=max_chars,
        force_full=force_full,
        include_vault=True,
    )
    nav_map = build_navigational_map(session, include_private=include_private, user_id=user_id)
    full_context = build_full_context(session, include_private=include_private, user_id=user_id)
    section_stats = _context_section_stats(context_text)
    return {
        "configured_mode": config.MEMORY_CONTEXT_MODE,
        "effective_mode": "full" if force_full or config.MEMORY_CONTEXT_MODE == "full" else "smart",
        "forced_full": force_full,
        "include_private": include_private,
        "active_chars": len(context_text),
        "prompt_budget_chars": max_chars,
        "nav_map_chars": len(nav_map),
        "full_context_chars": len(full_context),
        "full_inline_threshold_chars": config.MEMORY_CONTEXT_FULL_INLINE_MAX_CHARS,
        "full_context_inline": "FULL STRUCTURED JOURNAL DATABASE" in context_text,
        "vault_inline": "EXPORTED VAULT FILE TEXT" in context_text,
        "sections": section_stats,
    }


def _format_context_diagnostics(info: dict) -> str:
    lines = [
        "Context diagnostics",
        f"Configured mode: {info['configured_mode']}",
        f"Effective mode: {info['effective_mode']}",
        f"Forced full audit: {info['forced_full']}",
        f"Confidential included: {info['include_private']}",
        f"Active package: {info['active_chars']:,} / {info['prompt_budget_chars']:,} chars",
        f"Navigation map: {info['nav_map_chars']:,} chars",
        f"Full database context: {info['full_context_chars']:,} chars",
        f"Full-inline threshold: {info['full_inline_threshold_chars']:,} chars",
        f"Full database inline: {info['full_context_inline']}",
        f"Vault text inline: {info['vault_inline']}",
        "",
        "Sections attached:",
    ]
    sections = info.get("sections") or []
    for section in sections[:20]:
        lines.append(f"- {section['title']}: {section['chars']:,} chars")
    if len(sections) > 20:
        lines.append(f"- ... {len(sections) - 20} more sections")
    if not sections:
        lines.append("- none")
    lines.extend(
        [
            "",
            "This report intentionally shows sizes and section names only, not memory text.",
        ]
    )
    return "\n".join(lines)
