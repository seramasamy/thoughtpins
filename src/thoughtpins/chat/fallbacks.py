"""Provider-independent replies for degraded chat operation."""

from __future__ import annotations


def fallback_conversation_reply(text: str) -> str:
    """Return a useful deterministic response when generation is unavailable."""
    lower = text.lower().strip()
    if any(word in lower for word in ("running", "runing", "working", "online", "alive")):
        return (
            "Telegram reached me. Use /status for the normal check or /doctor for the deeper "
            "backend check. You can also chat here or send a journal note."
        )
    if lower in {"test", "testing"} or lower.startswith("testing "):
        return (
            "Test received. The Telegram bridge is alive. Send a journal note to save it, "
            "or ask me something about your entries."
        )
    if "what's up" in lower or "whats up" in lower or lower in {"yo", "sup", "hey", "hi", "hello"}:
        return "Here. You can chat normally, ask about your journal, or drop a life note and I will save it."
    if "thank" in lower:
        return "Anytime. Send the next thought when it is ready."
    return (
        "I can chat, answer from your journal, or save life notes. If you want something "
        "stored, say it naturally; if you just want to talk, keep it casual."
    )
