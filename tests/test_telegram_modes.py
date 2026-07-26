from __future__ import annotations

from pathlib import Path
from uuid import uuid4


def _set_config(monkeypatch, config, key: str, value):
    monkeypatch.setattr(config, key, value)
    monkeypatch.setattr(type(config), key, value)


def test_telegram_test_mode_claims_first_user(monkeypatch):
    from thoughtpins.bot import auth as bot_auth
    from thoughtpins.config import config

    path = Path(".tmp") / "test-telegram" / f"{uuid4().hex}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(bot_auth, "_test_user_path", lambda: path)
    monkeypatch.setattr(config, "TELEGRAM_ALLOWED_USER_IDS", [])
    monkeypatch.setattr(type(config), "TELEGRAM_ALLOWED_USER_IDS", [])
    _set_config(monkeypatch, config, "TELEGRAM_TEST_MODE", True)
    _set_config(monkeypatch, config, "ENVIRONMENT", "development")

    assert bot_auth.is_user_allowed(111) is True
    assert bot_auth.is_user_allowed(111) is True
    assert bot_auth.is_user_allowed(222) is False


def test_founder_personality_is_local_only(monkeypatch):
    from thoughtpins.bot.personality import get_visible_personalities
    from thoughtpins.config import config

    _set_config(monkeypatch, config, "ENABLE_FOUNDER_MODE", False)
    _set_config(monkeypatch, config, "ENVIRONMENT", "development")
    assert "founder" not in get_visible_personalities()

    _set_config(monkeypatch, config, "ENABLE_FOUNDER_MODE", True)
    assert "founder" in get_visible_personalities()

    _set_config(monkeypatch, config, "ENVIRONMENT", "production")
    assert "founder" not in get_visible_personalities()


def test_confidential_mode_requires_configured_code(monkeypatch):
    from thoughtpins.bot import disclosure
    from thoughtpins.config import config

    path = Path(".tmp") / "test-disclosure" / f"{uuid4().hex}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(disclosure, "_state_path", lambda: path)
    disclosure._disclosure_state.clear()
    disclosure._pending_confirmation.clear()

    _set_config(monkeypatch, config, "CONFIDENTIAL_ACCESS_CODE", "")
    _set_config(monkeypatch, config, "FOUNDER_ACCESS_CODE", "")
    assert disclosure.try_enable("chat-1", "anything") is False

    _set_config(monkeypatch, config, "CONFIDENTIAL_ACCESS_CODE", "local-code")
    assert disclosure.try_enable("chat-1", "wrong") is False
    assert disclosure.try_enable("chat-1", "local-code") is True
    assert disclosure.is_disclosure_mode("chat-1") is True


def test_telegram_startup_validation_for_founder_mode(monkeypatch):
    from thoughtpins.config import config

    _set_config(monkeypatch, config, "ENABLE_TELEGRAM_BOT", True)
    _set_config(monkeypatch, config, "TELEGRAM_BOT_TOKEN", "123456789:abcdefghijklmnopqrstuvwxyzABC")
    _set_config(monkeypatch, config, "TELEGRAM_TEST_MODE", True)
    _set_config(monkeypatch, config, "ENABLE_FOUNDER_MODE", True)
    _set_config(monkeypatch, config, "FOUNDER_ACCESS_CODE", "founder-local")
    _set_config(monkeypatch, config, "CONFIDENTIAL_ACCESS_CODE", "private-local")
    _set_config(monkeypatch, config, "ENVIRONMENT", "development")
    _set_config(monkeypatch, config, "TELEGRAM_ALLOWED_USER_IDS", [])

    assert config.validate_telegram_startup() == []

    _set_config(monkeypatch, config, "ENVIRONMENT", "production")
    problems = config.validate_telegram_startup()

    assert any("TELEGRAM_TEST_MODE" in problem for problem in problems)
    assert any("ENABLE_FOUNDER_MODE" in problem for problem in problems)


def test_locked_local_telegram_uses_dedicated_bound_user(isolated_db, monkeypatch):
    from thoughtpins.config import config
    from thoughtpins.db import User
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user, get_or_create_user_for_telegram

    _set_config(monkeypatch, config, "SYSTEM_LOCKED", True)
    _set_config(monkeypatch, config, "TELEGRAM_TEST_MODE", True)
    _set_config(monkeypatch, config, "ENVIRONMENT", "development")

    session = get_session()
    try:
        app_user = User(
            display_name="Existing app user",
            api_key="existing-app-user-key",
            auth_method="password",
        )
        session.add(app_user)
        session.commit()

        default_user = get_or_create_default_user(session=session)
        telegram_user = get_or_create_user_for_telegram("local-founder-chat", session=session)

        assert default_user.id != app_user.id
        assert default_user.is_admin is True
        assert telegram_user.id not in {app_user.id, default_user.id}
        assert telegram_user.auth_method == "telegram"
        assert telegram_user.telegram_chat_id == "local-founder-chat"
    finally:
        session.close()


def test_founder_ops_reports_jobs_without_secrets(isolated_db, monkeypatch):
    from thoughtpins.config import config
    from thoughtpins.db import IngestionJob
    from thoughtpins.founder.ops import build_doctor_report, build_jobs_report
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram

    _set_config(monkeypatch, config, "TELEGRAM_BOT_TOKEN", "123456789:abcdefghijklmnopqrstuvwxyzABC")
    _set_config(monkeypatch, config, "TELEGRAM_TEST_MODE", True)
    _set_config(monkeypatch, config, "LLM_API_KEY", "secret-llm-key")
    _set_config(monkeypatch, config, "LLM_PROVIDER", "openai_compatible")
    _set_config(monkeypatch, config, "LLM_MODEL", "llm-test")

    session = get_session()
    try:
        user = get_or_create_user_for_telegram("chat-1", session=session)
        session.add(IngestionJob(user_id=user.id, raw_text="hello", status="failed", source="telegram", error="boom"))
        session.commit()

        doctor, ok = build_doctor_report(session, user_id=user.id, chat_id="chat-1")
        jobs = build_jobs_report(session, user_id=user.id)

        assert ok is True
        assert "database" in doctor
        assert "configured endpoint" in doctor
        assert "llm-test" not in doctor
        assert "secret-llm-key" not in doctor
        assert "failed: 1" in jobs
        assert "boom" in jobs
    finally:
        session.close()


def test_llm_display_model_label_is_normalized():
    from thoughtpins.llm.client import normalize_llm_model_name

    assert normalize_llm_model_name("vendor-chat[large]") == "vendor-chat"
    assert normalize_llm_model_name('"vendor-chat[large]"') == "vendor-chat"
    assert normalize_llm_model_name("") == "chat-model"


def test_telegram_conversation_fallback_is_useful():
    from thoughtpins.bot.commands import _fallback_conversation_reply

    testing = _fallback_conversation_reply("testing")
    status = _fallback_conversation_reply("everyhitng runing ?")
    casual = _fallback_conversation_reply("whats up bro")

    assert "Telegram bridge is alive" in testing
    assert "Use /status" in status
    assert "chat normally" in casual
    assert "What's on your mind" not in testing + status + casual


def test_telegram_save_reply_is_clean():
    from thoughtpins.bot.commands import _format_journal_stored_reply

    response = _format_journal_stored_reply(
        {
            "stats": {
                "memories": 2,
                "entities": 1,
                "events": 0,
                "relationships": 1,
                "action_items": 1,
            }
        },
        elapsed=1.9,
    )

    assert response.startswith("Saved.\n")
    assert "Captured: 2 memories, 1 entity, 1 link, 1 action item." in response
    assert "Entry stored" not in response


def test_telegram_classifier_handles_casual_and_query_boundaries():
    from thoughtpins.ingestion.classify import classify_message

    assert classify_message("whats up bro")["type"] == "conversation"
    assert classify_message("everyhitng runing ?")["type"] == "conversation"
    assert classify_message("which one won?")["type"] == "query"


def test_conversation_context_includes_full_memory_actions_and_vault(isolated_db, monkeypatch, tmp_path):
    from datetime import datetime

    from thoughtpins.bot.commands import build_conversation_memory_context
    from thoughtpins.config import config
    from thoughtpins.db import ActionItem, Memory, RawEntry
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram
    from thoughtpins.utils import hash_text

    _set_config(monkeypatch, config, "VAULT_PATH", tmp_path / "vault")

    session = get_session()
    try:
        user = get_or_create_user_for_telegram("chat-context", session=session)
        raw = RawEntry(
            user_id=user.id,
            raw_text="I refactored the memory router and need to clean the apartment tomorrow.",
            content_hash=hash_text("context test raw"),
            telegram_chat_id="chat-context",
            processed_status="completed",
            local_date=datetime(2026, 5, 23).date(),
            local_time="10:00",
        )
        session.add(raw)
        session.flush()
        session.add(
            Memory(
                user_id=user.id,
                raw_entry_id=raw.id,
                memory_type="user_action",
                text="User refactored the memory router.",
                local_date=datetime(2026, 5, 23).date(),
            )
        )
        session.add(
            ActionItem(
                user_id=user.id,
                raw_entry_id=raw.id,
                description="clean the apartment",
                due_at=datetime(2026, 5, 24, 9, 0),
                status="open",
            )
        )
        session.commit()

        vault_file = config.vault_path() / user.id / "01_Daily" / "2026-05-23.md"
        vault_file.parent.mkdir(parents=True, exist_ok=True)
        vault_file.write_text("Vault note: memory router refactor.", encoding="utf-8")

        context = build_conversation_memory_context(
            session,
            chat_id="chat-context",
            include_private=False,
            user_id=user.id,
            max_chars=80_000,
        )

        assert "NAVIGATIONAL MEMORY MAP" in context
        assert "FULL STRUCTURED JOURNAL DATABASE" in context
        assert "ACTION ITEMS" in context
        assert "clean the apartment" in context
        assert "User refactored the memory router." in context
        assert "Vault note: memory router refactor." in context
    finally:
        session.close()


def test_smart_context_slices_large_library_and_keeps_relevant_memory(isolated_db, monkeypatch):
    from datetime import datetime

    from thoughtpins.bot.commands import build_conversation_memory_context
    from thoughtpins.config import config
    from thoughtpins.db import Memory, RawEntry
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram
    from thoughtpins.utils import hash_text

    _set_config(monkeypatch, config, "MEMORY_CONTEXT_MODE", "smart")
    _set_config(monkeypatch, config, "MEMORY_CONTEXT_FULL_INLINE_MAX_CHARS", 10)
    _set_config(monkeypatch, config, "MEMORY_CONTEXT_RELEVANT_MEMORIES", 5)
    _set_config(monkeypatch, config, "MEMORY_CONTEXT_RECENT_MEMORIES", 2)
    _set_config(monkeypatch, config, "MEMORY_CONTEXT_RECENT_ENTRIES", 2)

    session = get_session()
    try:
        user = get_or_create_user_for_telegram("chat-smart-context", session=session)
        raw_relevant = RawEntry(
            user_id=user.id,
            raw_text="Maya said the memory layer should feel trustworthy.",
            content_hash=hash_text("smart relevant"),
            telegram_chat_id="chat-smart-context",
            processed_status="completed",
            local_date=datetime(2026, 5, 20).date(),
            local_time="10:00",
        )
        raw_recent = RawEntry(
            user_id=user.id,
            raw_text="Recent unrelated errand note.",
            content_hash=hash_text("smart recent"),
            telegram_chat_id="chat-smart-context",
            processed_status="completed",
            local_date=datetime(2026, 5, 24).date(),
            local_time="11:00",
        )
        session.add_all([raw_relevant, raw_recent])
        session.flush()
        session.add_all(
            [
                Memory(
                    user_id=user.id,
                    raw_entry_id=raw_relevant.id,
                    memory_type="decision",
                    text="Maya said the memory layer should feel trustworthy.",
                    local_date=datetime(2026, 5, 20).date(),
                ),
                Memory(
                    user_id=user.id,
                    raw_entry_id=raw_recent.id,
                    memory_type="observation",
                    text="User bought paper towels.",
                    local_date=datetime(2026, 5, 24).date(),
                ),
            ]
        )
        session.commit()

        context = build_conversation_memory_context(
            session,
            chat_id="chat-smart-context",
            query="what did Maya say about the memory layer?",
            include_private=False,
            user_id=user.id,
            max_chars=20_000,
        )

        assert "NAVIGATIONAL MEMORY MAP" in context
        assert "FULL STRUCTURED JOURNAL DATABASE" not in context
        assert "QUERY-RELEVANT MEMORIES" in context
        assert "Maya said the memory layer should feel trustworthy." in context
        assert "RAW ENTRY EXCERPTS" in context
    finally:
        session.close()


def test_answer_with_llm_can_force_full_context(isolated_db, monkeypatch):
    from datetime import datetime

    from thoughtpins.bot import commands
    from thoughtpins.config import config
    from thoughtpins.db import Memory, RawEntry
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram
    from thoughtpins.utils import hash_text

    captured: list[str] = []

    class CapturingLlm:
        def chat(self, messages, **kwargs):
            captured.append(messages[-1]["content"])
            return "ok"

    _set_config(monkeypatch, config, "MEMORY_CONTEXT_MODE", "smart")
    _set_config(monkeypatch, config, "MEMORY_CONTEXT_FULL_INLINE_MAX_CHARS", 10)
    monkeypatch.setattr(commands, "get_llm_client", lambda: CapturingLlm())

    session = get_session()
    try:
        user = get_or_create_user_for_telegram("chat-force-full", session=session)
        raw = RawEntry(
            user_id=user.id,
            raw_text="The founder audit needs exact raw context.",
            content_hash=hash_text("force full"),
            telegram_chat_id="chat-force-full",
            processed_status="completed",
            local_date=datetime(2026, 5, 24).date(),
            local_time="12:00",
        )
        session.add(raw)
        session.flush()
        session.add(
            Memory(
                user_id=user.id,
                raw_entry_id=raw.id,
                memory_type="observation",
                text="The founder audit needs exact raw context.",
                local_date=datetime(2026, 5, 24).date(),
            )
        )
        session.commit()

        commands.answer_with_llm("founder audit?", session, user_id=user.id)
        commands.answer_with_llm("founder audit?", session, user_id=user.id, force_full_context=True)

        assert "FULL STRUCTURED JOURNAL DATABASE" not in captured[0]
        assert "FULL STRUCTURED JOURNAL DATABASE" in captured[1]
    finally:
        session.close()


def test_conversation_history_retains_longer_local_chat_memory(monkeypatch, tmp_path):
    from thoughtpins.bot import commands

    monkeypatch.setattr(commands, "_cache_path", lambda: tmp_path / "conversation_cache.json")
    commands.CONVERSATION_CACHE.clear()

    history: list[dict] = []
    for i in range(120):
        commands._remember_conversation_turn("chat-history", history, f"user {i}", f"assistant {i}")
        history = commands.CONVERSATION_CACHE["chat-history"]

    retained = commands.CONVERSATION_CACHE["chat-history"]
    prompt_history = commands._history_for_prompt(retained, max_chars=10_000)

    assert len(retained) == commands._CONVERSATION_HISTORY_MAX_MESSAGES
    assert retained[0]["content"] == "user 20"
    assert retained[-1]["content"] == "assistant 119"
    assert prompt_history[-1]["content"] == "assistant 119"


def test_full_context_renders_expenses_without_crashing(isolated_db):
    from datetime import datetime

    from thoughtpins.bot.commands import build_full_context
    from thoughtpins.db import Entity, Expense, RawEntry
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram
    from thoughtpins.utils import hash_text

    session = get_session()
    try:
        user = get_or_create_user_for_telegram("chat-expense", session=session)
        raw = RawEntry(
            user_id=user.id,
            raw_text="I spent $12 at Blue Bottle for coffee.",
            content_hash=hash_text("expense context"),
            telegram_chat_id="chat-expense",
            processed_status="completed",
            local_date=datetime(2026, 5, 23).date(),
            local_time="11:30",
        )
        merchant = Entity(user_id=user.id, type="place", canonical_name="Blue Bottle")
        session.add_all([raw, merchant])
        session.flush()
        session.add(
            Expense(
                user_id=user.id,
                raw_entry_id=raw.id,
                amount=12.0,
                currency="USD",
                merchant_or_place_entity_id=merchant.id,
                reason="coffee",
                category="food",
            )
        )
        session.commit()

        context = build_full_context(session, include_private=False, user_id=user.id)

        assert "## EXPENSES" in context
        assert "12.0 USD at Blue Bottle: coffee [food]" in context
    finally:
        session.close()


async def test_handle_conversation_sends_memory_vault_and_history_to_llm(
    isolated_db,
    monkeypatch,
    tmp_path,
):
    from datetime import datetime

    from thoughtpins.bot import commands
    from thoughtpins.config import config
    from thoughtpins.db import ActionItem, Memory, RawEntry
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram
    from thoughtpins.utils import hash_text

    class FakeChat:
        def __init__(self):
            self.actions: list[str] = []

        async def send_action(self, action: str) -> None:
            self.actions.append(action)

    class FakeMessage:
        def __init__(self, chat_id: str):
            self.chat_id = chat_id
            self.chat = FakeChat()
            self.replies: list[str] = []

        async def reply_text(self, text: str, **kwargs) -> None:
            self.replies.append(text)

    class FakeUpdate:
        def __init__(self, chat_id: str):
            self.message = FakeMessage(chat_id)

    class CapturingLlm:
        def __init__(self):
            self.messages: list[dict] = []

        def chat(self, messages: list[dict], temperature: float, max_tokens: int) -> str:
            self.messages = messages
            return "You were working on the memory router, and the apartment reminder is still open."

    _set_config(monkeypatch, config, "VAULT_PATH", tmp_path / "vault")
    monkeypatch.setattr(commands, "_cache_path", lambda: tmp_path / "conversation_cache.json")
    commands.CONVERSATION_CACHE.clear()
    commands.CONVERSATION_CACHE["chat-prompt"] = [
        {"role": "user", "content": "Earlier chat about launch nerves."},
        {"role": "assistant", "content": "I remember that pressure around launch."},
    ]
    llm = CapturingLlm()
    monkeypatch.setattr(commands, "get_llm_client", lambda: llm)

    session = get_session()
    try:
        user = get_or_create_user_for_telegram("chat-prompt", session=session)
        raw = RawEntry(
            user_id=user.id,
            raw_text="I refactored the Telegram memory prompt and need to clean the apartment tomorrow.",
            content_hash=hash_text("prompt memory context"),
            telegram_chat_id="chat-prompt",
            processed_status="completed",
            local_date=datetime(2026, 5, 23).date(),
            local_time="12:15",
        )
        session.add(raw)
        session.flush()
        session.add(
            Memory(
                user_id=user.id,
                raw_entry_id=raw.id,
                memory_type="user_action",
                text="User refactored the Telegram memory prompt.",
                local_date=datetime(2026, 5, 23).date(),
            )
        )
        session.add(
            ActionItem(
                user_id=user.id,
                raw_entry_id=raw.id,
                description="clean the apartment",
                due_at=datetime(2026, 5, 24, 9, 0),
                status="open",
            )
        )
        session.commit()

        vault_file = config.vault_path() / user.id / "01_Daily" / "2026-05-23.md"
        vault_file.parent.mkdir(parents=True, exist_ok=True)
        vault_file.write_text("Vault note: Telegram prompt refactor.", encoding="utf-8")
    finally:
        session.close()

    update = FakeUpdate("chat-prompt")
    await commands.handle_conversation(update, "what should I remember from yesterday?")

    assert update.message.chat.actions == ["typing"]
    assert update.message.replies == [
        "You were working on the memory router, and the apartment reminder is still open."
    ]
    assert len(llm.messages) >= 4
    system_prompt = llm.messages[0]["content"]
    evidence_prompt = llm.messages[-1]["content"]
    assert "MEMORY EVIDENCE SECURITY BOUNDARY" in system_prompt
    assert "User refactored the Telegram memory prompt." not in system_prompt
    assert "LONG-TERM MEMORY EVIDENCE FOR THIS REQUEST" in evidence_prompt
    assert "FULL STRUCTURED JOURNAL DATABASE" in evidence_prompt
    assert "User refactored the Telegram memory prompt." in evidence_prompt
    assert "clean the apartment" in evidence_prompt
    assert "Vault note: Telegram prompt refactor." in evidence_prompt
    assert any(message["content"] == "Earlier chat about launch nerves." for message in llm.messages)
    assert commands.CONVERSATION_CACHE["chat-prompt"][-2]["content"] == "what should I remember from yesterday?"


def test_answer_with_llm_empty_response_uses_local_memory_fallback(isolated_db, monkeypatch):
    from datetime import datetime

    from thoughtpins.bot import commands
    from thoughtpins.db import ActionItem, Memory, RawEntry
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram
    from thoughtpins.utils import hash_text

    class EmptyLlm:
        def chat(self, messages: list[dict], temperature: float, max_tokens: int) -> str:
            return ""

    monkeypatch.setattr(commands, "get_llm_client", lambda: EmptyLlm())

    session = get_session()
    try:
        user = get_or_create_user_for_telegram("chat-empty-answer", session=session)
        raw = RawEntry(
            user_id=user.id,
            raw_text="Tomorrow remind me to draft the privacy policy checklist.",
            content_hash=hash_text("empty answer fallback"),
            telegram_chat_id="chat-empty-answer",
            processed_status="completed",
            local_date=datetime(2026, 5, 24).date(),
            local_time="09:00",
        )
        session.add(raw)
        session.flush()
        session.add(
            Memory(
                user_id=user.id,
                raw_entry_id=raw.id,
                memory_type="future_plan",
                text="User needs to draft the privacy policy checklist.",
                local_date=datetime(2026, 5, 24).date(),
            )
        )
        session.add(
            ActionItem(
                user_id=user.id,
                raw_entry_id=raw.id,
                description="draft the privacy policy checklist",
                due_at=datetime(2026, 5, 25, 10, 0),
                status="open",
            )
        )
        session.commit()

        answer = commands.answer_with_llm(
            "what reminders exist about the privacy policy?",
            session,
            user_id=user.id,
        )

        assert "saved memory" in answer
        assert "draft the privacy policy checklist" in answer
        assert "2026-05-25 10:00" in answer
    finally:
        session.close()


async def test_handle_conversation_empty_llm_uses_memory_fallback(isolated_db, monkeypatch, tmp_path):
    from datetime import datetime

    from thoughtpins.bot import commands
    from thoughtpins.db import Memory, RawEntry
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram
    from thoughtpins.utils import hash_text

    class FakeChat:
        async def send_action(self, action: str) -> None:
            pass

    class FakeMessage:
        def __init__(self, chat_id: str):
            self.chat_id = chat_id
            self.chat = FakeChat()
            self.replies: list[str] = []

        async def reply_text(self, text: str, **kwargs) -> None:
            self.replies.append(text)

    class FakeUpdate:
        def __init__(self, chat_id: str):
            self.message = FakeMessage(chat_id)

    class EmptyLlm:
        def chat(self, messages: list[dict], temperature: float, max_tokens: int) -> str:
            return ""

    monkeypatch.setattr(commands, "_cache_path", lambda: tmp_path / "conversation_cache.json")
    commands.CONVERSATION_CACHE.clear()
    monkeypatch.setattr(commands, "get_llm_client", lambda: EmptyLlm())

    session = get_session()
    try:
        user = get_or_create_user_for_telegram("chat-empty-conversation", session=session)
        raw = RawEntry(
            user_id=user.id,
            raw_text="Dana decided reliability should come before UI polish.",
            content_hash=hash_text("empty conversation fallback"),
            telegram_chat_id="chat-empty-conversation",
            processed_status="completed",
            local_date=datetime(2026, 5, 24).date(),
            local_time="09:00",
        )
        session.add(raw)
        session.flush()
        session.add(
            Memory(
                user_id=user.id,
                raw_entry_id=raw.id,
                memory_type="decision",
                text="Dana decided reliability should come before UI polish.",
                local_date=datetime(2026, 5, 24).date(),
            )
        )
        session.commit()
    finally:
        session.close()

    update = FakeUpdate("chat-empty-conversation")
    await commands.handle_conversation(update, "what do you remember about reliability?")

    assert update.message.replies
    assert "saved memory" in update.message.replies[0]
    assert "reliability should come before UI polish" in update.message.replies[0]


async def test_handle_conversation_persists_chat_and_style_profile(isolated_db, monkeypatch, tmp_path):
    from thoughtpins.bot import commands
    from thoughtpins.bot.style_memory import CHAT_SOURCE, CHAT_STATUS
    from thoughtpins.db import RawEntry, User
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram

    class FakeFromUser:
        id = 4242

    class FakeChat:
        async def send_action(self, action: str) -> None:
            pass

    class FakeMessage:
        def __init__(self):
            self.chat_id = "chat-style"
            self.message_id = 501
            self.from_user = FakeFromUser()
            self.chat = FakeChat()
            self.replies: list[str] = []

        async def reply_text(self, text: str, **kwargs) -> None:
            self.replies.append(text)

    class FakeUpdate:
        def __init__(self):
            self.message = FakeMessage()

    class CapturingLlm:
        def __init__(self):
            self.messages: list[dict] = []

        def chat(self, messages: list[dict], temperature: float, max_tokens: int) -> str:
            self.messages = messages
            return "yeah, I remember the vibe. what's on your mind?"

    monkeypatch.setattr(commands, "_cache_path", lambda: tmp_path / "conversation_cache.json")
    commands.CONVERSATION_CACHE.clear()
    llm = CapturingLlm()
    monkeypatch.setattr(commands, "get_llm_client", lambda: llm)

    session = get_session()
    try:
        get_or_create_user_for_telegram("chat-style", session=session)
        session.commit()
    finally:
        session.close()

    update = FakeUpdate()
    await commands.handle_conversation(update, "yo bro whats up")

    assert update.message.replies == ["yeah, I remember the vibe. what's on your mind?"]
    assert "USER STYLE MEMORY" in llm.messages[0]["content"]
    assert "yo bro whats up" in llm.messages[-1]["content"]

    session = get_session()
    try:
        user = session.query(User).filter(User.telegram_chat_id == "chat-style").one()
        entry = session.query(RawEntry).filter(RawEntry.user_id == user.id).one()
        assert entry.source == CHAT_SOURCE
        assert entry.processed_status == CHAT_STATUS
        assert entry.raw_text == "yo bro whats up"
        style = user.preferences_json["style_profile"]
        assert style["message_count"] >= 1
        assert "bro" in style["casual_marker_counts"]
    finally:
        session.close()


async def test_handler_defaults_ambiguous_thought_to_chat(monkeypatch):
    import thoughtpins.bot.processing as processing
    from thoughtpins.bot import handlers
    from thoughtpins.bot.natural_commands import clear_pending

    class FakeMessage:
        def __init__(self):
            self.text = "I think memory is mostly attention"
            self.chat_id = "chat-ambiguous"
            self.replies: list[str] = []

        async def reply_text(self, text: str, **kwargs) -> None:
            self.replies.append(text)

    class FakeUpdate:
        def __init__(self):
            self.message = FakeMessage()

    clear_pending("chat-ambiguous")

    async def no_disclosure(update, text: str) -> bool:
        return False

    monkeypatch.setattr(handlers, "handle_disclosure_code", no_disclosure)
    monkeypatch.setattr(processing, "is_processing", lambda chat_id: False)
    from thoughtpins.chat.engine import ChatRouteDecision

    monkeypatch.setattr(
        handlers,
        "route_chat_message",
        lambda text: ChatRouteDecision(
            route_type="ambiguous",
            routed_text=text,
            classification={"type": "ambiguous"},
        ),
    )

    routed: list[str] = []

    async def fake_durable(update, text: str) -> None:
        routed.append(text)
        await update.message.reply_text("chat ok")

    monkeypatch.setattr(handlers, "_execute_durable_chat_turn", fake_durable)

    update = FakeUpdate()
    await handlers.handle_natural_language(update, type("FakeContext", (), {"args": []})())

    assert routed == ["I think memory is mostly attention"]
    assert update.message.replies == ["chat ok"]


async def test_handler_persists_durable_telegram_chat_thread(isolated_db, monkeypatch, tmp_path):
    import thoughtpins.bot.processing as processing
    from thoughtpins.bot import commands, handlers
    from thoughtpins.db import ChatConversation, ChatMessage, RawEntry, User
    from thoughtpins.store import get_session

    class FakeUser:
        id = 777

    class FakeChat:
        def __init__(self):
            self.actions: list[str] = []

        async def send_action(self, action: str) -> None:
            self.actions.append(action)

    class FakeMessage:
        def __init__(self):
            self.text = "yo bro whats up"
            self.chat_id = "chat-durable"
            self.message_id = 701
            self.from_user = FakeUser()
            self.chat = FakeChat()
            self.replies: list[str] = []

        async def reply_text(self, text: str, **kwargs) -> None:
            self.replies.append(text)

    class FakeUpdate:
        def __init__(self):
            self.message = FakeMessage()

    class FakeLlm:
        def chat(self, messages: list[dict], temperature: float, max_tokens: int) -> str:
            assert "USER STYLE MEMORY" in messages[0]["content"]
            return "yeah, I'm here."

    async def no_disclosure(update, text: str) -> bool:
        return False

    monkeypatch.setattr(handlers, "handle_disclosure_code", no_disclosure)
    monkeypatch.setattr(processing, "is_processing", lambda chat_id: False)
    monkeypatch.setattr(commands, "_cache_path", lambda: tmp_path / "conversation_cache.json")
    commands.CONVERSATION_CACHE.clear()
    monkeypatch.setattr(commands, "get_llm_client", lambda: FakeLlm())

    update = FakeUpdate()
    await handlers.handle_natural_language(update, type("FakeContext", (), {"args": []})())

    assert update.message.chat.actions == ["typing"]
    assert update.message.replies == ["yeah, I'm here."]

    session = get_session()
    try:
        user = session.query(User).filter(User.telegram_chat_id == "chat-durable").one()
        conversation = (
            session.query(ChatConversation)
            .filter(ChatConversation.user_id == user.id, ChatConversation.conversation_key == "telegram:chat-durable")
            .one()
        )
        messages = (
            session.query(ChatMessage)
            .filter(ChatMessage.conversation_id == conversation.id)
            .order_by(ChatMessage.created_at_utc.asc(), ChatMessage.id.asc())
            .all()
        )
        assert [message.role for message in messages] == ["user", "assistant"]
        assert messages[0].text == "yo bro whats up"
        assert messages[1].text == "yeah, I'm here."

        entry = session.query(RawEntry).filter(RawEntry.user_id == user.id).one()
        assert entry.source == "telegram_chat"
        assert entry.processed_status == "conversation"
        assert entry.telegram_chat_id == "telegram:chat-durable"
    finally:
        session.close()


async def test_handler_confirms_durable_telegram_undo(isolated_db, monkeypatch):
    from datetime import datetime

    import thoughtpins.bot.processing as processing
    from thoughtpins.bot import handlers
    from thoughtpins.db import PendingChatAction, RawEntry
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram
    from thoughtpins.utils import hash_text

    class FakeUser:
        id = 888

    class FakeMessage:
        def __init__(self, text: str):
            self.text = text
            self.chat_id = "chat-durable-undo"
            self.message_id = 801
            self.from_user = FakeUser()
            self.replies: list[str] = []

        async def reply_text(self, text: str, **kwargs) -> None:
            self.replies.append(text)

    class FakeUpdate:
        def __init__(self, text: str):
            self.message = FakeMessage(text)

    async def no_disclosure(update, text: str) -> bool:
        return False

    monkeypatch.setattr(handlers, "handle_disclosure_code", no_disclosure)
    monkeypatch.setattr(processing, "is_processing", lambda chat_id: False)
    monkeypatch.setattr("thoughtpins.chat.engine._refresh_vectors_after_removed_memories", lambda *args, **kwargs: None)

    session = get_session()
    try:
        user = get_or_create_user_for_telegram("chat-durable-undo", session=session)
        raw = RawEntry(
            user_id=user.id,
            raw_text="Today I saved a throwaway test entry.",
            content_hash=hash_text("durable telegram undo"),
            telegram_chat_id="telegram:chat-durable-undo",
            source="telegram_chat",
            processed_status="completed",
            local_date=datetime(2026, 6, 1).date(),
            local_time="12:00",
        )
        session.add(raw)
        session.commit()
        raw_id = raw.id
        user_id = user.id
    finally:
        session.close()

    first = FakeUpdate("undo that")
    await handlers.handle_natural_language(first, type("FakeContext", (), {"args": []})())
    assert "confirm undo" in first.message.replies[0].lower()

    session = get_session()
    try:
        pending = session.query(PendingChatAction).filter(PendingChatAction.user_id == user_id).one()
        assert pending.status == "pending"
    finally:
        session.close()

    second = FakeUpdate("confirm undo")
    await handlers.handle_natural_language(second, type("FakeContext", (), {"args": []})())
    assert "Undid latest saved item" in second.message.replies[0]

    session = get_session()
    try:
        assert session.get(RawEntry, raw_id) is None
        pending = session.query(PendingChatAction).filter(PendingChatAction.user_id == user_id).one()
        assert pending.status == "confirmed"
    finally:
        session.close()


async def test_cmd_mark_chat_demotes_latest_journal_save(isolated_db, monkeypatch):
    from datetime import datetime

    from thoughtpins.bot import commands
    from thoughtpins.bot.style_memory import CHAT_SOURCE, CHAT_STATUS
    from thoughtpins.db import Memory, RawEntry
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram
    from thoughtpins.utils import hash_text

    class FakeMessage:
        chat_id = "chat-demote"
        replies: list[str]

        def __init__(self):
            self.replies = []

        async def reply_text(self, text: str, **kwargs) -> None:
            self.replies.append(text)

    class FakeUpdate:
        def __init__(self):
            self.message = FakeMessage()

    monkeypatch.setattr(commands, "_refresh_vectors_after_removed_memories", lambda *args, **kwargs: None)

    session = get_session()
    try:
        user = get_or_create_user_for_telegram("chat-demote", session=session)
        raw = RawEntry(
            user_id=user.id,
            raw_text="Today I saved something that should have been plain chat.",
            content_hash=hash_text("demote journal"),
            telegram_chat_id="chat-demote",
            source="telegram",
            processed_status="completed",
            local_date=datetime(2026, 5, 24).date(),
            local_time="09:00",
        )
        session.add(raw)
        session.flush()
        session.add(
            Memory(
                user_id=user.id,
                raw_entry_id=raw.id,
                memory_type="thought",
                text="User saved something that should have been plain chat.",
                local_date=datetime(2026, 5, 24).date(),
            )
        )
        raw_id = raw.id
        session.commit()
    finally:
        session.close()

    update = FakeUpdate()
    await commands.cmd_mark_chat(update, type("FakeContext", (), {"args": []})())

    assert "Marked the latest saved entry as chat memory" in update.message.replies[0]
    session = get_session()
    try:
        raw = session.get(RawEntry, raw_id)
        assert raw.source == CHAT_SOURCE
        assert raw.processed_status == CHAT_STATUS
        assert session.query(Memory).filter(Memory.raw_entry_id == raw_id).count() == 0
    finally:
        session.close()


async def test_telegram_long_essay_routes_as_single_entry(monkeypatch):
    from thoughtpins.bot import handlers

    class FakeMessage:
        def __init__(self, text: str):
            self.text = text
            self.chat_id = "chat-essay"
            self.replies: list[str] = []

        async def reply_text(self, text: str, **kwargs) -> None:
            self.replies.append(text)

    class FakeUpdate:
        def __init__(self, text: str):
            self.message = FakeMessage(text)

    async def no_disclosure(update, text: str) -> bool:
        return False

    async def fake_durable(update, text: str) -> None:
        processed_texts.append(text)
        await update.message.reply_text("Saved.")

    essay = ("today " + ("I tested a long Telegram journal essay with memory routing. " * 180)).strip()
    processed_texts: list[str] = []
    monkeypatch.setattr(handlers, "handle_disclosure_code", no_disclosure)
    from thoughtpins.chat.engine import ChatRouteDecision

    monkeypatch.setattr(
        handlers,
        "route_chat_message",
        lambda text: ChatRouteDecision(
            route_type="journal_entry",
            routed_text=text,
            classification={"type": "journal_entry"},
        ),
    )
    monkeypatch.setattr(handlers, "_execute_durable_chat_turn", fake_durable)

    update = FakeUpdate(essay)
    await handlers.handle_natural_language(update, type("FakeContext", (), {"args": []})())

    assert processed_texts == [essay]
    assert update.message.replies == ["Saved."]
