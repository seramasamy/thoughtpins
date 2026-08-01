from __future__ import annotations

import pytest
from fakes.telegram import FakeTelegramContext, FakeTelegramUpdate


@pytest.fixture(autouse=True)
def no_processing(telegram_bot, monkeypatch):
    # Depends on telegram_bot so the skip happens before this autouse fixture
    # reaches for thoughtpins.bot.handlers, which imports the telegram package.
    import thoughtpins.bot.processing as processing
    from thoughtpins.bot import handlers
    from thoughtpins.bot.natural_commands import clear_pending

    async def no_disclosure(update, text: str) -> bool:
        return False

    clear_pending("chat-e2e")
    clear_pending("chat-e2e-restricted")
    monkeypatch.setattr(handlers, "handle_disclosure_code", no_disclosure)
    monkeypatch.setattr(processing, "is_processing", lambda chat_id: False)


async def test_fake_telegram_e2e_public_article_link_routes_to_document_memory(telegram_bot, isolated_db, monkeypatch):
    from thoughtpins import library
    from thoughtpins.bot import handlers
    from thoughtpins.db import DocumentSource, User
    from thoughtpins.library import FetchedSource
    from thoughtpins.store import get_session

    monkeypatch.setattr(library, "_index_document_memories", lambda memories: None)
    monkeypatch.setattr(library, "schedule_document_memory_indexing", lambda memories: None)

    def fake_fetch(url: str) -> FetchedSource:
        return FetchedSource(
            original_url=url,
            url=url,
            title="Harness Public Article",
            text=(
                "This public article explains durable Telegram document ingestion, "
                "source provenance, and second-brain recall. "
            )
            * 20,
            status="processed",
            source_domain="example.com",
            access_method="public_fetch",
            rights_basis="public_web",
            fetch_status="fetched",
            canonical_url=url,
            retrieval_quality_score=1.0,
        )

    monkeypatch.setattr(library, "fetch_url_text", fake_fetch)

    update = FakeTelegramUpdate("read this https://example.com/public-memory-test")
    await handlers.handle_natural_language(update, FakeTelegramContext())

    assert update.message.chat.actions == ["typing"]
    assert update.message.replies[-1].startswith("Saved source: Harness Public Article")
    assert "searchable sections" in update.message.replies[-1]
    assert "public_fetch" not in update.message.replies[-1]

    session = get_session()
    try:
        user = session.query(User).filter(User.telegram_chat_id == "chat-e2e").one()
        doc = session.query(DocumentSource).filter(DocumentSource.user_id == user.id).one()
        assert doc.title == "Harness Public Article"
        assert doc.status == "processed"
        assert doc.source_url == "https://example.com/public-memory-test"
        assert doc.access_method == "public_fetch"
    finally:
        session.close()


async def test_fake_telegram_e2e_restricted_article_link_keeps_reference_without_body(
    telegram_bot, isolated_db, monkeypatch
):
    from thoughtpins import library
    from thoughtpins.bot import handlers
    from thoughtpins.db import DocumentSource
    from thoughtpins.library import FetchedSource
    from thoughtpins.store import get_session

    monkeypatch.setattr(library, "_index_document_memories", lambda memories: None)
    monkeypatch.setattr(library, "schedule_document_memory_indexing", lambda memories: None)

    def fake_fetch(url: str) -> FetchedSource:
        return FetchedSource(
            original_url=url,
            url=url,
            title="WSJ Restricted Story",
            text="",
            status="needs_text",
            error="This publisher is treated as subscription/restricted content.",
            source_domain="wsj.com",
            access_method="metadata_only",
            rights_basis="metadata_only",
            fetch_status="restricted",
            canonical_url=url,
            paywall_detected=True,
        )

    monkeypatch.setattr(library, "fetch_url_text", fake_fetch)

    update = FakeTelegramUpdate(
        "read this https://www.wsj.com/articles/long-running-ai-agents-are-here-3e3aa89b",
        chat_id="chat-e2e-restricted",
    )
    await handlers.handle_natural_language(update, FakeTelegramContext())

    reply = update.message.replies[-1]
    assert "Saved source link: WSJ Restricted Story" in reply
    assert "authorized open copy" in reply
    assert "metadata_only" not in reply
    assert "title, link, and any notes you add" in reply

    session = get_session()
    try:
        doc = session.query(DocumentSource).one()
        assert doc.title == "WSJ Restricted Story"
        assert doc.status == "needs_text"
        assert doc.rights_basis == "metadata_only"
        assert doc.paywall_detected is True
    finally:
        session.close()


async def test_fake_telegram_e2e_ops_command_uses_extracted_ops_module(telegram_bot, monkeypatch):
    from thoughtpins.bot import handlers

    called: dict[str, list[str]] = {}

    async def fake_doctor(update, context) -> None:
        called["doctor"] = list(context.args)
        await update.message.reply_text("doctor ok")

    monkeypatch.setattr(handlers, "cmd_doctor", fake_doctor)

    update = FakeTelegramUpdate("run a health check")
    await handlers.handle_natural_language(update, FakeTelegramContext())

    assert called == {"doctor": []}
    assert update.message.replies == ["doctor ok"]


async def test_fake_telegram_e2e_plain_chat_uses_durable_engine(telegram_bot, monkeypatch):
    from thoughtpins.bot import handlers

    routed: list[str] = []

    async def fake_durable(update, text: str) -> None:
        routed.append(text)
        await update.message.reply_text("chat ok")

    monkeypatch.setattr(handlers, "_execute_durable_chat_turn", fake_durable)

    update = FakeTelegramUpdate("hey what's up")
    await handlers.handle_natural_language(update, FakeTelegramContext())

    assert routed == ["hey what's up"]
    assert update.message.replies == ["chat ok"]
