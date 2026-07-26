from __future__ import annotations

import json

from thoughtpins.chat.conversation_state import (
    HISTORY_MAX_MESSAGES,
    history_for_prompt,
    load_conversation_cache,
    remember_conversation_turn,
    save_conversation_cache,
)


def test_conversation_cache_round_trip_is_atomic_and_bounded(tmp_path):
    path = tmp_path / "conversation_cache.json"
    cache: dict[str, list[dict[str, str]]] = {}
    history = [{"role": "user", "content": f"message {index}"} for index in range(HISTORY_MAX_MESSAGES + 20)]

    remember_conversation_turn(
        "review-chat",
        history,
        "latest question",
        "latest answer",
        cache=cache,
        persist=lambda: save_conversation_cache(cache, path=path),
    )

    assert path.exists()
    assert not path.with_suffix(".json.tmp").exists()
    assert len(cache["review-chat"]) == HISTORY_MAX_MESSAGES
    assert json.loads(path.read_text(encoding="utf-8")) == cache


def test_conversation_cache_rejects_invalid_messages_without_replacing_object(tmp_path):
    path = tmp_path / "conversation_cache.json"
    path.write_text(
        json.dumps(
            {
                "valid-chat": [
                    {"role": "user", "content": "keep"},
                    {"role": "administrator", "content": "discard"},
                    {"role": "assistant", "content": 42},
                ],
                "invalid-chat": "not a history",
            }
        ),
        encoding="utf-8",
    )
    cache: dict[str, list[dict[str, str]]] = {"old": [{"role": "user", "content": "old"}]}
    identity = id(cache)

    assert load_conversation_cache(cache, path=path) is True
    assert id(cache) == identity
    assert cache == {"valid-chat": [{"role": "user", "content": "keep"}]}


def test_prompt_history_keeps_the_newest_complete_turns():
    history = [
        {"role": "user", "content": "old " * 30},
        {"role": "assistant", "content": "middle " * 30},
        {"role": "user", "content": "newest question"},
        {"role": "assistant", "content": "newest answer"},
    ]

    selected = history_for_prompt(history, max_chars=80)

    assert selected == history[-2:]
