"""Disclosure mode manager -- controls whether private entries are included in queries.

Standard mode (default): Private entries excluded from context, search, and answers.
Disclosure mode: All entries (normal + private) included.

Two-step enable flow:
  1. User: /disclosure on
  2. Bot: "Enter disclosure code to confirm:"
  3. User: the configured CONFIDENTIAL_ACCESS_CODE
  4. Bot: "Disclosure mode enabled."

State persists to a JSON file so it survives bot restarts.
"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from thoughtpins.config import config
from thoughtpins.privacy import fingerprint_identifier

DISCLOSURE_CODE = ""

# In-memory state: chat_id -> bool
_disclosure_state: dict[str, bool] = {}

# Pending confirmation: chat_id -> True (awaiting code entry)
_pending_confirmation: set[str] = set()


def _state_path() -> Path:
    return config.resolve_path("./data/disclosure_state.json")


def load_state():
    """Load persisted disclosure states from disk."""
    global _disclosure_state
    path = _state_path()
    if path.exists():
        try:
            _disclosure_state = json.loads(path.read_text(encoding="utf-8"))
            logger.debug("Loaded disclosure state: {} chats", len(_disclosure_state))
        except Exception as e:
            logger.warning("Could not load disclosure state: {}", e)
            _disclosure_state = {}
    else:
        _disclosure_state = {}


def save_state():
    """Persist disclosure states to disk."""
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_disclosure_state), encoding="utf-8")


def is_disclosure_mode(chat_id: str) -> bool:
    """Check if disclosure mode is active for a chat."""
    return _disclosure_state.get(chat_id, False)


def set_disclosure_mode(chat_id: str, enabled: bool):
    """Enable or disable disclosure mode for a chat."""
    _disclosure_state[chat_id] = enabled
    save_state()
    state = "ENABLED" if enabled else "DISABLED"
    logger.info("Disclosure mode {} for chat_hash={}", state, fingerprint_identifier(chat_id))


def try_enable(chat_id: str, code: str) -> bool:
    """Try to enable disclosure mode with a code. Returns True if successful."""
    expected = config.CONFIDENTIAL_ACCESS_CODE.strip() or config.FOUNDER_ACCESS_CODE.strip()
    if not expected:
        logger.warning("Confidential mode requested but no access code is configured")
        return False
    if code.strip() == expected:
        set_disclosure_mode(chat_id, True)
        return True
    return False


# -- Two-step confirmation flow --


def is_pending_confirmation(chat_id: str) -> bool:
    """Check if this chat is awaiting disclosure code entry."""
    return chat_id in _pending_confirmation


def start_confirmation(chat_id: str):
    """Mark chat as awaiting disclosure code."""
    _pending_confirmation.add(chat_id)


def clear_confirmation(chat_id: str):
    """Clear the pending confirmation state."""
    _pending_confirmation.discard(chat_id)


# Load state on import
load_state()
