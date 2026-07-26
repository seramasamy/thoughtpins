"""Durable chat memory and conservative user style adaptation."""

from __future__ import annotations

import re
from collections import Counter
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from thoughtpins.chat.message_memory import CHAT_SOURCE, CHAT_STATUS, is_chat_memory_entry
from thoughtpins.db import RawEntry, User
from thoughtpins.utils import hash_text, local_now, utcnow

__all__ = [
    "CHAT_SOURCE",
    "CHAT_STATUS",
    "build_user_style_prompt",
    "build_user_style_prompt_from_profile",
    "is_chat_memory_entry",
    "record_user_style_sample",
    "remember_user_chat_message",
]


STYLE_PROFILE_KEY = "style_profile"
MAX_STYLE_SAMPLES = 40
MAX_TRACKED_TOKENS = 80

_STOP_WORDS = {
    "a",
    "about",
    "actually",
    "after",
    "again",
    "all",
    "also",
    "am",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "because",
    "been",
    "but",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "how",
    "i",
    "if",
    "im",
    "in",
    "is",
    "it",
    "its",
    "just",
    "like",
    "me",
    "my",
    "of",
    "on",
    "or",
    "our",
    "so",
    "that",
    "the",
    "this",
    "to",
    "was",
    "we",
    "what",
    "when",
    "where",
    "who",
    "why",
    "with",
    "would",
    "you",
    "your",
}

_CASUAL_MARKERS = {
    "bro",
    "bruh",
    "lol",
    "lmao",
    "haha",
    "btw",
    "ngl",
    "imo",
    "tbh",
    "fr",
    "rn",
    "idk",
    "kinda",
    "sorta",
    "gonna",
    "wanna",
    "gotta",
    "u",
    "ur",
    "ya",
    "yo",
    "sup",
}


def remember_user_chat_message(
    session: Session,
    *,
    user_id: str,
    chat_id: str,
    text: str,
    telegram_message_id: str = "",
    author_user_id: str = "",
    source: str = CHAT_SOURCE,
) -> RawEntry | None:
    """Persist a casual Telegram turn as chat memory and update style profile.

    Conversation turns are stored as raw chat entries, not structured journal
    extractions. This keeps recall complete while avoiding noisy entity/memory
    graph pollution from greetings and short back-and-forth.
    """
    cleaned = _clean_text(text)
    if not cleaned:
        return None

    now_utc = utcnow()
    now_local = local_now()
    source = (source or CHAT_SOURCE)[:32]
    content_hash = _chat_hash(cleaned, source=source)
    existing = (
        session.query(RawEntry)
        .filter(
            RawEntry.user_id == user_id,
            RawEntry.source == source,
            RawEntry.content_hash == content_hash,
            RawEntry.created_at_utc >= now_utc - timedelta(minutes=15),
        )
        .first()
    )
    if existing is None:
        existing = RawEntry(
            user_id=user_id,
            created_at_utc=now_utc,
            local_date=now_local.date(),
            local_time=now_local.strftime("%H:%M"),
            source=source,
            telegram_message_id=str(telegram_message_id) if telegram_message_id else "",
            telegram_chat_id=str(chat_id) if chat_id else "",
            author_user_id=str(author_user_id) if author_user_id else "",
            raw_text=cleaned,
            content_hash=content_hash,
            is_private=False,
            sensitivity="personal",
            processed_status=CHAT_STATUS,
        )
        session.add(existing)
        session.flush()

    record_user_style_sample(session, user_id=user_id, text=cleaned)
    session.commit()
    return existing


def record_user_style_sample(session: Session, *, user_id: str, text: str) -> None:
    """Update the user's rolling style profile from any user-authored text."""
    cleaned = _clean_text(text)
    if not cleaned:
        return
    user = session.get(User, user_id)
    if not user:
        return

    prefs = dict(user.preferences_json or {})
    profile = dict(prefs.get(STYLE_PROFILE_KEY) or {})
    count = int(profile.get("message_count") or 0) + 1
    previous_avg = float(profile.get("avg_message_chars") or 0.0)
    profile["message_count"] = count
    profile["avg_message_chars"] = round(previous_avg + ((len(cleaned) - previous_avg) / min(count, 200)), 2)
    profile["last_updated_utc"] = utcnow().isoformat()

    samples = [str(item) for item in profile.get("sample_phrases") or [] if str(item).strip()]
    sample_key = cleaned.lower()
    if len(cleaned) <= 280 and sample_key not in {sample.lower() for sample in samples[-MAX_STYLE_SAMPLES:]}:
        samples.append(cleaned)
    profile["sample_phrases"] = samples[-MAX_STYLE_SAMPLES:]

    token_counts = Counter(
        {str(token): int(value) for token, value in dict(profile.get("token_counts") or {}).items() if str(token)}
    )
    casual_counts = Counter(
        {
            str(token): int(value)
            for token, value in dict(profile.get("casual_marker_counts") or {}).items()
            if str(token)
        }
    )
    for token in _tokens(cleaned):
        if token in _CASUAL_MARKERS:
            casual_counts[token] += 1
        elif token not in _STOP_WORDS:
            token_counts[token] += 1

    profile["token_counts"] = dict(token_counts.most_common(MAX_TRACKED_TOKENS))
    profile["casual_marker_counts"] = dict(casual_counts.most_common(30))
    profile["question_ratio"] = _rolling_ratio(profile.get("question_ratio"), cleaned.endswith("?"), count)
    profile["lowercase_ratio"] = _rolling_ratio(
        profile.get("lowercase_ratio"),
        cleaned == cleaned.lower() and any(char.isalpha() for char in cleaned),
        count,
    )
    profile["exclamation_ratio"] = _rolling_ratio(profile.get("exclamation_ratio"), "!" in cleaned, count)

    prefs[STYLE_PROFILE_KEY] = profile
    user.preferences_json = prefs


def build_user_style_prompt(session: Session, user_id: str | None, *, response_style: str = "friendly") -> str:
    """Return a compact prompt block describing the user's rolling chat style."""
    if not user_id:
        return ""
    user = session.get(User, user_id)
    if not user:
        return ""
    profile = (user.preferences_json or {}).get(STYLE_PROFILE_KEY) or {}
    return build_user_style_prompt_from_profile(profile, response_style=response_style)


def build_user_style_prompt_from_profile(profile: dict[str, Any], *, response_style: str = "friendly") -> str:
    count = int(profile.get("message_count") or 0)
    if count <= 0:
        return ""

    samples = [str(sample).strip() for sample in profile.get("sample_phrases") or [] if str(sample).strip()]
    tokens = list(dict(profile.get("token_counts") or {}).keys())[:12]
    casual = list(dict(profile.get("casual_marker_counts") or {}).keys())[:10]
    avg_chars = int(float(profile.get("avg_message_chars") or 0))
    question_ratio = float(profile.get("question_ratio") or 0.0)
    lowercase_ratio = float(profile.get("lowercase_ratio") or 0.0)

    lines = [
        "## USER STYLE MEMORY",
        "Adapt gently to the user's preferred pacing and level of detail over time.",
        "Use this as tone calibration, not as permission to impersonate the user.",
        f"Observed user-authored messages: {count}",
    ]
    if avg_chars:
        lines.append(f"Average message length: about {avg_chars} characters.")
    if tokens:
        lines.append("Recurring user vocabulary: " + ", ".join(tokens))
    if casual and response_style == "mirror":
        lines.append("Casual markers the user uses: " + ", ".join(casual))
    if question_ratio >= 0.35:
        lines.append("The user often asks directly; answer without making them use commands.")
    if lowercase_ratio >= 0.45 and response_style == "mirror":
        lines.append("The user often writes casually/lowercase; keep replies natural and low-friction.")
    if samples and response_style == "mirror":
        lines.append("Recent style samples:")
        for sample in samples[-6:]:
            lines.append(f"- {sample[:220]}")
    if response_style == "mirror":
        lines.extend(
            [
                "Response style rule: mirror broad pacing, directness, and vocabulary lightly, while staying clear, stable, and respectful.",
                "Use slang sparingly. Do not mimic typos aggressively and never claim to be the user.",
            ]
        )
    else:
        lines.extend(
            [
                "Response style rule: remain friendly and professional. Adapt length and directness, but not slang or misspellings.",
                "Do not copy pet names or forms of address. Never call the user bro, bruh, dude, buddy, or my friend.",
            ]
        )
    return "\n".join(lines)


def _chat_hash(text: str, *, source: str = CHAT_SOURCE) -> str:
    return hash_text(f"{source}:{text}")


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9_'-]{1,}", text.lower())


def _rolling_ratio(previous: Any, new_value: bool, count: int) -> float:
    previous_value = float(previous or 0.0)
    return round(previous_value + ((1.0 if new_value else 0.0) - previous_value) / min(count, 200), 4)
