"""Production personality system: public modes plus optional local founder test mode."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from loguru import logger

from thoughtpins.config import config
from thoughtpins.db import RawEntry, User
from thoughtpins.llm.client import get_llm_client
from thoughtpins.store import get_session


@dataclass
class PersonalityProfile:
    id: str
    name: str
    description: str
    tone: str
    voice_instruction: str


PREDEFINED: dict[str, PersonalityProfile] = {
    "friendly": PersonalityProfile(
        id="friendly",
        name="Friendly & Professional",
        description="Warm, clear, and polished without forced familiarity.",
        tone="warm, clear, professional",
        voice_instruction=(
            "You are a friendly, professional journal companion. Be warm, attentive, clear, and "
            "grounded without sounding corporate or overly familiar. Reference the user's retained "
            "memories and sources with specificity. Be encouraging when appropriate and tactful "
            "about difficult moments. Do not copy slang, typos, pet names, or casual forms of address "
            "from the user; never call the user 'bro', 'bruh', 'dude', or 'buddy'. Avoid canned therapy "
            "language and unnecessary exclamation marks. Do not give medical, legal, or financial advice."
        ),
    ),
    "clear": PersonalityProfile(
        id="clear",
        name="Clear & Concise",
        description="Direct, structured, and efficient.",
        tone="direct, concise, structured",
        voice_instruction=(
            "You are a clear, efficient journal companion. Answer directly, structure lists when "
            "useful, and cite concrete dates or facts from the user's journal. Be precise without "
            "being cold. Do not speculate beyond the journal. Do not use slang, pet names, or casual "
            "forms of address."
        ),
    ),
    "mirror": PersonalityProfile(
        id="mirror",
        name="Match My Style",
        description="Adapts to the user's writing style with conservative calibration.",
        tone="adaptive, measured, journal-derived",
        voice_instruction=(
            "You are an adaptive journal companion. Mirror the user's broad communication style, "
            "but stay more measured than the source material. Match formality and analytical depth "
            "when helpful. Never amplify extreme emotional states, never replicate vulgarity or "
            "slurs, and never claim to be the user."
        ),
    ),
    "founder": PersonalityProfile(
        id="founder",
        name="Founder Test Mode",
        description="Fast, direct, product-focused local test voice.",
        tone="direct, pragmatic, product-focused",
        voice_instruction=(
            "You are operating in local founder test mode for the journal product owner. "
            "Be direct, pragmatic, and implementation-aware. Prefer concise answers, expose "
            "system state clearly, and call out uncertainty. Still follow all memory rules: "
            "never invent journal facts, never reveal private entries unless confidential mode "
            "is enabled, and never include secrets or raw credentials."
        ),
    ),
}


def is_founder_mode_available() -> bool:
    return bool(config.ENABLE_FOUNDER_MODE and not config.is_production())


def get_visible_personalities(chat_id: str | None = None) -> dict[str, PersonalityProfile]:
    profiles = dict(PREDEFINED)
    if not is_founder_mode_available():
        profiles.pop("founder", None)
    return profiles


def _personality_path() -> Path:
    return config.resolve_path("./data/personality.json")


def _normalize_personality_id(personality_id: str | None) -> str:
    if personality_id == "founder" and not is_founder_mode_available():
        return "clear"
    if personality_id in PREDEFINED:
        return personality_id
    legacy_map = {
        "warm_friend": "friendly",
        "analytical_coach": "clear",
        "derived": "mirror",
        "witty_intellectual": "clear",
        "stoic_laconic": "clear",
    }
    return legacy_map.get(personality_id or "", "friendly")


def load_personality(chat_id: str | None = None) -> str:
    """Load the active personality ID."""
    path = _personality_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if chat_id:
                chat_data = (data.get("by_chat") or {}).get(str(chat_id)) or {}
                if chat_data.get("personality"):
                    return _normalize_personality_id(chat_data.get("personality"))
            return _normalize_personality_id(data.get("personality"))
        except Exception as e:
            logger.warning("Personality load error: {}", e)
    return "friendly"


def save_personality(personality_id: str, chat_id: str | None = None) -> bool:
    """Persist the user's personality choice."""
    personality_id = _normalize_personality_id(personality_id)
    if personality_id not in get_visible_personalities():
        return False
    path = _personality_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    if chat_id:
        by_chat = existing.setdefault("by_chat", {})
        chat_data = by_chat.setdefault(str(chat_id), {})
        chat_data["personality"] = personality_id
    else:
        existing["personality"] = personality_id
    path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    return True


def get_active_profile(chat_id: str | None = None) -> PersonalityProfile:
    personality_id = load_personality(chat_id)
    profile = PREDEFINED.get(personality_id, PREDEFINED["friendly"])

    if personality_id == "mirror":
        path = _personality_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("mirror_voice"):
                    return PersonalityProfile(
                        id="mirror",
                        name="Mirror",
                        description="Adapted from recent journal style.",
                        tone=data.get("mirror_tone", "adaptive"),
                        voice_instruction=data["mirror_voice"],
                    )
            except Exception:
                pass
    return profile


def get_response_profile(session, user_id: str | None, chat_id: str | None = None) -> PersonalityProfile:
    """Resolve a tenant-scoped product voice, with Telegram's explicit mode as fallback."""
    if session is not None and user_id:
        user = session.get(User, user_id)
        app_preferences = dict(((user.preferences_json if user else {}) or {}).get("app_preferences") or {})
        response_style = str(app_preferences.get("response_style") or "").strip().lower()
        if response_style in {"friendly", "clear", "mirror"}:
            return PREDEFINED[response_style]

    # Product conversation keys are shared labels within a tenant, not personality IDs.
    # They must not inherit a machine-wide local testing personality.
    if chat_id and ":" not in chat_id:
        return get_active_profile(chat_id)
    return PREDEFINED["friendly"]


def enforce_response_style(text: str, profile_id: str) -> str:
    """Remove unrequested direct-address slang from non-mirroring product voices."""
    cleaned = (text or "").strip()
    if not cleaned or profile_id == "mirror":
        return cleaned

    address = r"(?:bro|bruh|dude|buddy|my friend)"
    cleaned, removed_prefix = re.subn(
        rf"(?i)^\s*(?:hey\s*[,!-]?\s*)?{address}\s*[,!:\-]*\s*",
        "",
        cleaned,
        count=1,
    )
    cleaned = re.sub(
        rf"(?i),\s*{address}(?=\s*(?:[,;:!?.\-]|$)|\s+[a-z])",
        "",
        cleaned,
    )
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    if removed_prefix and cleaned[:1].islower():
        cleaned = cleaned[:1].upper() + cleaned[1:]
    return cleaned.strip()


MIRROR_DERIVATION_PROMPT = """Analyze the user's communication style from these journal and chat entries.
Return only valid JSON.

Identify:
- formality: casual, neutral, or formal
- vocabulary: simple, moderate, or advanced
- humor_style: none, dry, or playful
- sentence_length: short, medium, or long
- emotional_openness: guarded, moderate, or open
- speech_patterns: up to 5 recurring phrases or patterns
- core_topics: up to 5 recurring topics
- description_style: factual, emotional, analytical, or mixed

Generate a conservative "mirror_voice" paragraph for an AI journal companion.
The voice may mirror broad style, but must be calmer and more measured than the user.
It must never use vulgarity, slurs, identity claims, manipulation, or extreme intensity.

JSON shape:
{
  "formality": "...",
  "vocabulary": "...",
  "humor_style": "...",
  "sentence_length": "...",
  "emotional_openness": "...",
  "speech_patterns": ["..."],
  "core_topics": ["..."],
  "description_style": "...",
  "mirror_voice": "..."
}
"""


def derive_personality_from_history(
    session=None,
    entry_limit: int = 30,
    user_id: str | None = None,
) -> Optional[str]:
    close_session = session is None
    if session is None:
        session = get_session()

    try:
        query = session.query(RawEntry).filter(
            RawEntry.is_private == False,
            RawEntry.processed_status.in_(["completed", "stored_private", "conversation"]),
        )
        if user_id:
            query = query.filter(RawEntry.user_id == user_id)
        entries = query.order_by(RawEntry.created_at_utc.desc()).limit(entry_limit).all()

        if len(entries) < 3:
            logger.info("Not enough entries for mirror personality derivation")
            return None

        combined = "\n\n---\n\n".join(entry.raw_text for entry in reversed(entries))
        response = get_llm_client().chat(
            [
                {"role": "system", "content": MIRROR_DERIVATION_PROMPT},
                {"role": "user", "content": f"Journal entries:\n\n{combined[:6000]}"},
            ],
            temperature=0.2,
            max_tokens=1024,
        )
        start = response.find("{")
        end = response.rfind("}")
        if start == -1 or end == -1:
            return None

        data = json.loads(response[start : end + 1])
        mirror_voice = data.get("mirror_voice", "")
        if not mirror_voice:
            return None

        path = _personality_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        existing: dict = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                existing = {}
        existing["personality"] = "mirror"
        existing["mirror_voice"] = mirror_voice
        existing["mirror_tone"] = data.get("formality", "adaptive")
        existing["mirror_analysis"] = {key: value for key, value in data.items() if key != "mirror_voice"}
        path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        logger.info("Mirror personality derived from {} entries", len(entries))
        return mirror_voice
    except Exception as e:
        logger.error("Mirror personality derivation failed: {}", e)
    finally:
        if close_session:
            session.close()

    return None


def get_conversation_system_prompt(
    chat_id: str | None = None,
    personality_profile: PersonalityProfile | None = None,
) -> str:
    """Build the system prompt for conversation mode."""
    profile = personality_profile or get_active_profile(chat_id)
    return f"""You are the user's personal journal companion and private memory assistant.

## Response Voice
Selected: {profile.name}
{profile.voice_instruction}

## Memory Rules
- Use the user's journal database when answering personal questions.
- Reference specific dates, people, and details when the journal supports them.
- Say "your journal shows" or "according to your entries" for personal facts.
- Never claim external truth about people in the user's life.
- Keep responses concise unless the user clearly asks for depth.

Current date: {_today_str()}."""


def _today_str() -> str:
    from thoughtpins.utils import local_today

    return local_today().isoformat()
