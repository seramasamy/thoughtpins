"""Processing state tracker — ETA, follow-up handling, per-chat state."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class ProcessingState:
    chat_id: str
    started_at: float
    text: str
    estimated_seconds: float = 240.0  # default 4 min
    follow_ups: list[str] = field(default_factory=list)
    status_msg_id: int | None = None

    @property
    def elapsed(self) -> float:
        return time.time() - self.started_at

    @property
    def remaining(self) -> float:
        return max(0, self.estimated_seconds - self.elapsed)

    @property
    def progress_pct(self) -> int:
        if self.estimated_seconds <= 0:
            return 50
        return min(95, int(100 * self.elapsed / self.estimated_seconds))

    def eta_text(self) -> str:
        r = self.remaining
        if r < 30:
            return "almost done"
        if r < 60:
            return f"~{int(r)}s remaining"
        return f"~{int(r / 60)}m {int(r % 60)}s remaining"

    def add_follow_up(self, text: str) -> bool:
        """Add a follow-up message. Returns True if it seems related to the entry."""
        # Simple heuristic: check if the follow-up shares words with the original
        orig_words = set(self.text.lower().split())
        follow_words = set(text.lower().split())
        overlap = orig_words & follow_words
        # If 3+ words overlap or follow-up is very short (<20 chars), it's likely related
        is_related = len(overlap) >= 3 or len(text) < 20
        self.follow_ups.append(text)
        if is_related:
            self.text += " " + text  # append to main text
        return is_related


# Per-chat processing state
_active: dict[str, ProcessingState] = {}

# ETA tracking: exponential moving average of seconds-per-char
_avg_spc: float = 0.9  # ~0.9 seconds per character (empirical from extraction logs)


def start_processing(chat_id: str, text: str) -> ProcessingState:
    """Mark a chat as currently processing a journal entry."""
    est = max(30, len(text) * _avg_spc * 0.7)  # 70% of avg time because LLM is variable
    state = ProcessingState(chat_id=chat_id, started_at=time.time(), text=text, estimated_seconds=est)
    _active[chat_id] = state
    return state


def finish_processing(chat_id: str, actual_seconds: float, text_len: int):
    """Mark processing complete and update ETA estimates."""
    global _avg_spc
    if chat_id in _active:
        del _active[chat_id]
    if text_len > 0:
        spc = actual_seconds / text_len
        _avg_spc = 0.8 * _avg_spc + 0.2 * spc  # EMA


def is_processing(chat_id: str) -> bool:
    return chat_id in _active


def get_state(chat_id: str) -> ProcessingState | None:
    return _active.get(chat_id)


def handle_follow_up(chat_id: str, text: str) -> str | None:
    """Handle a message received while processing. Returns a response or None."""
    state = _active.get(chat_id)
    if not state:
        return None

    is_related = state.add_follow_up(text)

    if is_related:
        return (
            f"I've added that to your current entry - it's still processing "
            f"({state.eta_text()}). I'll let you know when it's done."
        )
    else:
        return f"Still processing your entry ({state.eta_text()}). I'll be done soon - your new message is queued."
