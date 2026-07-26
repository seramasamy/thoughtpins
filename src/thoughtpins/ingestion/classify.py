"""Message classification -- determine intent before processing."""

from __future__ import annotations

import json
import re

from loguru import logger

from thoughtpins.llm.client import get_llm_client
from thoughtpins.llm.prompts import QUERY_CLASSIFY_PROMPT

# Patterns that signal casual conversation (not journal entries)
CONVERSATION_PATTERNS = [
    # Greetings
    "hi",
    "hello",
    "hey",
    "good morning",
    "good evening",
    "good night",
    "good afternoon",
    "morning",
    "evening",
    "yo",
    "sup",
    "heyy",
    "hii",
    # Social check-ins
    "how are you",
    "how's it going",
    "how are things",
    "how have you been",
    "what's up",
    "whats up",
    "how do you feel",
    "how're you",
    "how you doing",
    "how ya doing",
    "how goes",
    # Farewells
    "bye",
    "goodbye",
    "see you",
    "later",
    "gn",
    "night",
    # Gratitude
    "thanks",
    "thank you",
    "appreciate it",
    "thx",
    "ty",
    # Bot-directed chat
    "who are you",
    "what are you",
    "tell me about yourself",
    "what can you do",
    "what do you know",
    "what do you think",
]

STATUS_CHECK_WORDS = ("running", "runing", "working", "online", "alive", "up")
STATUS_TARGET_WORDS = ("you", "bot", "system", "everything", "everyhitng", "all", "telegram")

JOURNAL_NOTE_STARTERS = (
    "bar note",
    "business idea",
    "coffee chat",
    "daily note",
    "date night note",
    "deep contemplative journal",
    "deep journal",
    "dinner note",
    "errand note",
    "journal",
    "journal note",
    "note:",
    "note to self",
    "quick bar note",
    "quick daily thought",
    "quick errand note",
    "quick journal",
    "quick note",
    "random thought",
    "recipe idea",
    "recipe note",
    "networking event note",
    "networking note",
    "small social read",
    "spiritual note",
    "thought:",
)


def classify_message(text: str) -> dict:
    """
    Classify a Telegram message into:
    journal_entry, query, report_request, correction, command, private_entry,
    conversation, document_link, document_text, mixed, ambiguous
    Falls back to heuristic if LLM unavailable.
    """
    text_stripped = text.strip()
    text_lower = text_stripped.lower()

    classifiers = (
        _classify_command_or_prefix,
        _classify_link_message,
        _classify_note_shape,
        _classify_short_message,
        _classify_semantic_intent,
        _classify_ambiguous_thought,
    )
    for classifier in classifiers:
        result = classifier(text_stripped, text_lower)
        if result is not None:
            return result
    return _classify_with_llm(text_stripped)


def _classify_command_or_prefix(text: str, text_lower: str) -> dict | None:
    if text.startswith("/"):
        return {"type": "command", "intent": "explicit bot command", "confidence": 1.0}
    return _classify_explicit_prefix(text, text_lower)


def _classify_link_message(text: str, text_lower: str) -> dict | None:
    urls = _extract_urls(text)
    if not urls:
        return None
    if _looks_like_document_request(text_lower):
        return {
            "type": "document_link",
            "intent": "save article or source link",
            "confidence": 0.95,
            "urls": urls,
        }
    if _looks_like_memory_or_life_update(text_lower) and _looks_like_question(text_lower):
        return {
            "type": "mixed",
            "intent": "journal update plus question with link",
            "confidence": 0.74,
            "urls": urls,
        }
    if len(text) < 300 and len(urls) == 1:
        return {
            "type": "document_link",
            "intent": "bare source link",
            "confidence": 0.82,
            "urls": urls,
        }
    return None


def _classify_note_shape(text: str, text_lower: str) -> dict | None:
    if _looks_like_journal_note(text_lower):
        return {"type": "journal_entry", "intent": "note-style journal entry", "confidence": 0.96}
    if len(text) > 1200 and not _looks_like_long_query(text_lower):
        return {"type": "journal_entry", "intent": "long-form journal note or essay", "confidence": 0.95}
    return None


def _classify_short_message(text: str, text_lower: str) -> dict | None:
    if len(text) >= 40:
        return None
    if _looks_like_status_check(text_lower):
        return {"type": "conversation", "intent": "bot status check", "confidence": 0.98}
    if any(_contains_phrase(text_lower, pattern) for pattern in CONVERSATION_PATTERNS):
        return {"type": "conversation", "intent": "casual chat", "confidence": 0.95}
    if text_lower.endswith("?"):
        return {"type": "query", "intent": "question or search request", "confidence": 0.82}
    question_words = ("what", "when", "who", "where", "why", "how")
    if len(text) < 25 and not text_lower.startswith(question_words):
        return {"type": "conversation", "intent": "short message, likely chat", "confidence": 0.82}
    return None


def _classify_semantic_intent(text: str, text_lower: str) -> dict | None:
    question_words = (
        "what",
        "when",
        "who",
        "where",
        "why",
        "how",
        "summarize",
        "show me",
        "generate",
        "create",
        "tell",
        "find",
        "search",
        "list",
        "explain",
        "describe",
    )
    is_question = text_lower.endswith("?") or (text_lower.startswith(question_words) and len(text) < 200)
    if is_question:
        direct_question = text_lower.startswith(("what", "when", "who", "where", "why", "how"))
        if _looks_like_memory_or_life_update(text_lower) and not direct_question:
            return {"type": "mixed", "intent": "life update plus question", "confidence": 0.72}
        return {"type": "query", "intent": "question or search request", "confidence": 0.84}
    report_words = ("report", "digest", "summary", "weekly", "monthly", "chart", "graph")
    if any(word in text_lower for word in report_words) and len(text) < 100:
        return {"type": "report_request", "intent": "report or summary request", "confidence": 0.9}
    correction_starters = ("actually", "correction", "i meant", "that's wrong", "change that")
    if text_lower.startswith(correction_starters):
        return {"type": "correction", "intent": "correction to previous entry", "confidence": 0.92}
    if _looks_like_document_text(text):
        return {"type": "document_text", "intent": "pasted article or document text", "confidence": 0.88}
    if _looks_like_memory_or_life_update(text_lower):
        return {"type": "journal_entry", "intent": "first-person life update", "confidence": 0.86}
    return None


def _classify_ambiguous_thought(text: str, text_lower: str) -> dict | None:
    chat_starters = (
        "i think",
        "i believe",
        "i wonder",
        "do you think",
        "what's your opinion",
        "can you explain",
        "help me understand",
        "i've been thinking about",
        "what does it mean",
        "how would you",
        "i feel like",
    )
    if len(text) >= 200 or not text_lower.startswith(chat_starters):
        return None
    return {
        "type": "ambiguous",
        "intent": "could be a thought to save or a conversation",
        "confidence": 0.52,
        "options": ["save", "chat"],
    }


def _classify_with_llm(text: str) -> dict:
    try:
        llm = get_llm_client()
        raw = llm.chat(
            [
                {"role": "system", "content": QUERY_CLASSIFY_PROMPT},
                {"role": "user", "content": f"Classify: {text[:500]}"},
            ],
            temperature=0.0,
            max_tokens=256,
        )
        result = _parse_json(raw)
        if result and "type" in result:
            logger.debug("LLM classified as: {}", result["type"])
            result.setdefault("confidence", 0.7)
            return result
    except Exception as e:
        logger.warning("LLM classification failed, using heuristic: {}", e)

    return {"type": "journal_entry", "intent": "life log or journal entry", "confidence": 0.62}


def _classify_explicit_prefix(text: str, text_lower: str) -> dict | None:
    if text_lower.startswith(("save:", "journal:", "log:", "note to self:")):
        return {"type": "journal_entry", "intent": "explicit save prefix", "confidence": 1.0}
    if text_lower.startswith(("chat:", "just chat:", "talk:")):
        return {"type": "conversation", "intent": "explicit chat prefix", "confidence": 1.0}
    if text_lower.startswith(("read:", "article:", "source:", "doc:", "document:")):
        urls = _extract_urls(text)
        msg_type = "document_link" if urls else "document_text"
        return {"type": msg_type, "intent": "explicit library source prefix", "confidence": 1.0, "urls": urls}
    return None


def _extract_urls(text: str) -> list[str]:
    pattern = re.compile(r"https?://[^\s<>\]\)\"']+", re.IGNORECASE)
    seen: set[str] = set()
    urls: list[str] = []
    for match in pattern.finditer(text):
        url = match.group(0).rstrip(".,;:")
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _looks_like_document_request(text_lower: str) -> bool:
    return any(
        _contains_phrase(text_lower, word)
        for word in (
            "article",
            "document",
            "source",
            "link",
            "read this",
            "save this",
            "i read",
            "i'm reading",
            "reading this",
            "library",
        )
    )


def _looks_like_document_text(text: str) -> bool:
    stripped = text.strip()
    lowered = stripped.lower()
    if len(stripped) < 900:
        return False
    article_markers = (
        "abstract",
        "introduction",
        "conclusion",
        "by ",
        "published",
        "copyright",
        "executive summary",
        "references",
        "table of contents",
    )
    return sum(1 for marker in article_markers if marker in lowered[:3000]) >= 2


def _looks_like_question(text_lower: str) -> bool:
    stripped = text_lower.strip()
    return stripped.endswith("?") or stripped.startswith(
        (
            "what ",
            "when ",
            "who ",
            "where ",
            "why ",
            "how ",
            "can you ",
            "could you ",
            "tell me ",
            "find ",
            "search ",
            "show me ",
        )
    )


def _looks_like_memory_or_life_update(text_lower: str) -> bool:
    first_person = any(
        _contains_phrase(text_lower, word)
        for word in (
            "i",
            "me",
            "my",
            "we",
            "our",
            "today",
            "yesterday",
            "tomorrow",
        )
    )
    life_verbs = (
        "worked",
        "met",
        "saw",
        "went",
        "had",
        "felt",
        "realized",
        "decided",
        "learned",
        "read",
        "talked",
        "called",
        "spent",
        "bought",
        "ate",
        "drank",
        "walked",
        "thought",
        "noticed",
        "remembered",
        "need to",
        "remind me",
        "should",
        "want to",
        "plan to",
        "trying to",
    )
    time_markers = (
        "today",
        "yesterday",
        "tomorrow",
        "tonight",
        "this morning",
        "this afternoon",
        "this evening",
        "last night",
        "next week",
    )
    return first_person and (
        any(_contains_phrase(text_lower, verb) for verb in life_verbs)
        or any(marker in text_lower for marker in time_markers)
    )


def _contains_phrase(text_lower: str, pattern: str) -> bool:
    """Match casual phrases on token boundaries so "hi" does not match "this"."""
    escaped = re.escape(pattern)
    return re.search(rf"(?<![a-z0-9_]){escaped}(?![a-z0-9_])", text_lower) is not None


def _looks_like_journal_note(text_lower: str) -> bool:
    candidates = [text_lower.strip()]
    if ":" in text_lower[:100]:
        candidates.append(text_lower.split(":", 1)[1].strip())
    return any(candidate.startswith(starter) for candidate in candidates for starter in JOURNAL_NOTE_STARTERS)


def _looks_like_status_check(text_lower: str) -> bool:
    return any(_contains_phrase(text_lower, word) for word in STATUS_CHECK_WORDS) and any(
        _contains_phrase(text_lower, word) for word in STATUS_TARGET_WORDS
    )


def _looks_like_long_query(text_lower: str) -> bool:
    stripped = text_lower.strip()
    if stripped.endswith("?"):
        return True
    query_starters = (
        "what ",
        "when ",
        "who ",
        "where ",
        "why ",
        "how ",
        "summarize ",
        "summary ",
        "show me ",
        "generate ",
        "create ",
        "tell me ",
        "find ",
        "search ",
        "list ",
        "explain ",
        "describe ",
        "can you ",
        "could you ",
        "please summarize ",
        "help me understand ",
    )
    return any(stripped.startswith(starter) for starter in query_starters)


def _parse_json(raw: str) -> dict | None:
    try:
        text = raw.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            return json.loads(text[start : end + 1])
        return json.loads(text)
    except json.JSONDecodeError:
        return None
