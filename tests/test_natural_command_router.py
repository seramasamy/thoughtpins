from __future__ import annotations

import pytest


class FakeUser:
    id = 12345


class FakeMessage:
    def __init__(self, text: str, chat_id: str = "chat-natural"):
        self.text = text
        self.chat_id = chat_id
        self.message_id = 100
        self.from_user = FakeUser()
        self.replies: list[str] = []

    async def reply_text(self, text: str, **kwargs) -> None:
        self.replies.append(text)


class FakeUpdate:
    def __init__(self, text: str, chat_id: str = "chat-natural"):
        self.message = FakeMessage(text, chat_id=chat_id)


class FakeContext:
    def __init__(self):
        self.args: list[str] = []


def test_natural_router_maps_safe_read_only_requests():
    from thoughtpins.bot.natural_commands import route_natural_command

    cases = {
        "what did I write recently?": ("recent", []),
        "show me today's notes": ("today", []),
        "search my memory for Maya and the bar": ("search", ["Maya and the bar"]),
        "show saved articles": ("library", []),
        "show source Memory Systems Essay": ("source", ["Memory", "Systems", "Essay"]),
        "run a health check": ("doctor", []),
        "audit my memory system": ("audit", []),
        "is everything running?": ("status", []),
        "that was just chat": ("mark_chat", []),
        "save that": ("save_last_chat", []),
    }

    for text, expected in cases.items():
        route = route_natural_command(text)
        assert route is not None
        assert route.action == expected[0]
        assert route.args == expected[1]
        assert route.needs_confirmation is False


def test_natural_router_requires_confirmation_for_risky_requests():
    from thoughtpins.bot.natural_commands import route_natural_command

    cases = {
        "undo last save": "undo",
        "undo that": "undo",
        "don't save that": "undo",
        "rebuild the memory index": "reindex",
        "backup my journal": "backup",
        "export my data": "export",
        "forget memory abc123def": "forget",
        "rename Mya to Maya": "rename",
        "merge Mya into Maya": "merge",
        "turn on confidential mode": "confidential",
    }

    for text, action in cases.items():
        route = route_natural_command(text)
        assert route is not None
        assert route.action == action
        assert route.needs_confirmation is True
        assert "confirm" in route.prompt.lower()


@pytest.mark.parametrize(
    "text",
    [
        "Date night note: tried the miso salmon recipe and talked about fall travel.",
        "Networking event note: met Priya, who is building compliance tooling.",
        "Recipe idea: roast carrots with tahini, lemon, cilantro, and pistachios.",
        "Quick bar note: the bartender at Lumen recommended the rye sour.",
        "Spiritual note: prayer felt less like asking and more like listening tonight.",
        "Business idea: local-first memory app with explicit recall diagnostics.",
        "Random thought: attention is a budget, not a mood.",
    ],
)
def test_natural_router_does_not_hijack_generated_journal_notes(text: str):
    from thoughtpins.bot.natural_commands import route_natural_command
    from thoughtpins.ingestion.classify import classify_message

    assert route_natural_command(text) is None
    assert classify_message(text)["type"] == "journal_entry"


async def test_handler_routes_safe_chat_surface_command_through_durable_engine(monkeypatch):
    import thoughtpins.bot.processing as processing
    from thoughtpins.bot import handlers
    from thoughtpins.bot.natural_commands import clear_pending

    clear_pending("chat-natural")
    monkeypatch.setattr(handlers, "handle_disclosure_code", _no_disclosure)
    monkeypatch.setattr(processing, "is_processing", lambda chat_id: False)

    routed: list[str] = []

    async def fake_durable(update, text: str) -> None:
        routed.append(text)
        await update.message.reply_text("recent ok")

    monkeypatch.setattr(handlers, "_execute_durable_chat_turn", fake_durable)

    update = FakeUpdate("what did I write recently?")
    await handlers.handle_natural_language(update, FakeContext())

    assert routed == ["what did I write recently?"]
    assert update.message.replies == ["recent ok"]


async def test_handler_keeps_legacy_ops_on_command_dispatch(monkeypatch):
    import thoughtpins.bot.processing as processing
    from thoughtpins.bot import handlers
    from thoughtpins.bot.natural_commands import clear_pending

    clear_pending("chat-natural")
    monkeypatch.setattr(handlers, "handle_disclosure_code", _no_disclosure)
    monkeypatch.setattr(processing, "is_processing", lambda chat_id: False)

    called: dict[str, list[str]] = {}

    async def fake_doctor(update, context) -> None:
        called["doctor"] = list(context.args)
        await update.message.reply_text("doctor ok")

    monkeypatch.setattr(handlers, "cmd_doctor", fake_doctor)

    update = FakeUpdate("run a health check")
    await handlers.handle_natural_language(update, FakeContext())

    assert called == {"doctor": []}
    assert update.message.replies == ["doctor ok"]


async def test_handler_routes_undo_confirmation_flow_to_durable_engine(monkeypatch):
    import thoughtpins.bot.processing as processing
    from thoughtpins.bot import handlers
    from thoughtpins.bot.natural_commands import clear_pending

    clear_pending("chat-natural")
    monkeypatch.setattr(handlers, "handle_disclosure_code", _no_disclosure)
    monkeypatch.setattr(processing, "is_processing", lambda chat_id: False)

    routed: list[str] = []

    async def fake_durable(update, text: str) -> None:
        routed.append(text)
        await update.message.reply_text("durable ok")

    monkeypatch.setattr(handlers, "_execute_durable_chat_turn", fake_durable)

    first = FakeUpdate("undo last save")
    await handlers.handle_natural_language(first, FakeContext())

    assert routed == ["undo last save"]
    assert first.message.replies == ["durable ok"]

    second = FakeUpdate("confirm undo")
    await handlers.handle_natural_language(second, FakeContext())

    assert routed == ["undo last save", "confirm undo"]
    assert second.message.replies == ["durable ok"]


async def test_handler_saves_generated_journal_examples(monkeypatch):
    import thoughtpins.bot.processing as processing
    from thoughtpins.bot import handlers
    from thoughtpins.bot.natural_commands import clear_pending

    clear_pending("chat-natural")
    monkeypatch.setattr(handlers, "handle_disclosure_code", _no_disclosure)
    monkeypatch.setattr(processing, "is_processing", lambda chat_id: False)

    processed: list[str] = []

    async def fake_durable(update, text: str) -> None:
        processed.append(text)
        await update.message.reply_text("saved")

    monkeypatch.setattr(handlers, "_execute_durable_chat_turn", fake_durable)

    examples = [
        "Date night note: we had ramen at Koyo and talked about renting near the park.",
        "Networking event note: met Daniel, who runs partnerships at a climate startup.",
        "Recipe note: chickpeas, tomato, cumin, garlic, lemon, parsley; save this combo.",
        "Quick daily thought: I should protect the first ninety minutes for deep work.",
        (
            "Deep contemplative journal: today felt scattered at first, but the long walk "
            "helped me notice that the anxiety was mostly unfinished planning."
        ),
    ]

    for text in examples:
        update = FakeUpdate(text)
        await handlers.handle_natural_language(update, FakeContext())
        assert update.message.replies == ["saved"]

    assert processed == examples


async def _no_disclosure(update, text: str) -> bool:
    return False
