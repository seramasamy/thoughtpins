"""A Telegram turn must not run its blocking work on the event loop.

`handle_conversation` is a coroutine, but the work inside it — tenant lookup,
retrieval, context assembly, and the model call — is ordinary synchronous code
that takes seconds. Running it inline meant the bot could not answer anyone
else, or even keep sending a typing action, until the model came back.

Passing tests do not prove this on their own: the old inline version produced
exactly the same reply. So this asserts the thing that actually changed, by
recording which thread the model call happens on.
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest


class _FakeChat:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def send_action(self, action: str) -> None:
        self.actions.append(action)


class _FakeMessage:
    def __init__(self, chat_id: str) -> None:
        self.chat_id = chat_id
        self.chat = _FakeChat()
        self.message_id = 4242
        self.from_user = None
        self.replies: list[str] = []

    async def reply_text(self, text: str, **kwargs) -> None:
        self.replies.append(text)


class _FakeUpdate:
    def __init__(self, chat_id: str) -> None:
        self.message = _FakeMessage(chat_id)


async def test_the_model_call_does_not_run_on_the_event_loop(telegram_bot, isolated_db, monkeypatch, tmp_path):
    from thoughtpins.bot import commands

    loop_thread = threading.get_ident()
    seen: dict[str, int] = {}

    class RecordingLlm:
        def chat(self, messages: list[dict], temperature: float, max_tokens: int) -> str:
            seen["thread"] = threading.get_ident()
            return "Noted."

    monkeypatch.setattr(commands, "_cache_path", lambda: tmp_path / "conversation_cache.json")
    monkeypatch.setattr("thoughtpins.chat.reply.get_llm_client", lambda: RecordingLlm())
    commands.CONVERSATION_CACHE.clear()

    update = _FakeUpdate("loop-safety")
    await commands.handle_conversation(update, "what did I do yesterday?")

    assert update.message.replies == ["Noted."]
    assert "thread" in seen, "the model was never called, so this proves nothing"
    assert seen["thread"] != loop_thread, "the blocking work still runs on the event loop"


async def test_the_loop_keeps_running_while_a_turn_is_in_flight(telegram_bot, isolated_db, monkeypatch, tmp_path):
    """The point of the thread: other coroutines still get scheduled.

    The tick count is sampled from inside the blocking call, on entry and exit.
    Measuring after the turn instead would pass either way, because a frozen
    loop catches up the moment it is released.
    """
    from thoughtpins.bot import commands

    ticks = {"n": 0}
    sampled: dict[str, int] = {}

    class BlockingLlm:
        def chat(self, messages: list[dict], temperature: float, max_tokens: int) -> str:
            sampled["entry"] = ticks["n"]
            deadline = time.monotonic() + 0.3
            while time.monotonic() < deadline:
                time.sleep(0.01)
            sampled["exit"] = ticks["n"]
            return "Noted."

    monkeypatch.setattr(commands, "_cache_path", lambda: tmp_path / "conversation_cache.json")
    monkeypatch.setattr("thoughtpins.chat.reply.get_llm_client", lambda: BlockingLlm())
    commands.CONVERSATION_CACHE.clear()

    async def heartbeat() -> None:
        while True:
            await asyncio.sleep(0.01)
            ticks["n"] += 1

    beat = asyncio.create_task(heartbeat())
    update = _FakeUpdate("loop-liveness")
    await commands.handle_conversation(update, "still there?")
    beat.cancel()
    with pytest.raises(asyncio.CancelledError):
        await beat

    assert update.message.replies == ["Noted."]
    assert sampled, "the model was never called, so this proves nothing"
    assert sampled["exit"] > sampled["entry"], (
        f"the event loop made no progress while the model call was in flight, ticks stayed at {sampled['entry']}"
    )
