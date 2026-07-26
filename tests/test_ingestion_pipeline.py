from __future__ import annotations


class _ProviderStatusError(RuntimeError):
    def __init__(self, status_code: int):
        super().__init__("provider failure")
        self.status_code = status_code


def test_non_retryable_provider_failure_is_stored_as_terminal_error(isolated_db, monkeypatch):
    from thoughtpins.db import RawEntry
    from thoughtpins.ingestion.pipeline import process_message
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user

    monkeypatch.setattr(
        "thoughtpins.ingestion.pipeline.classify_message",
        lambda text: {"type": "journal_entry", "intent": "test"},
    )
    monkeypatch.setattr(
        "thoughtpins.ingestion.pipeline.extract_from_entry",
        lambda text, local_datetime: (_ for _ in ()).throw(_ProviderStatusError(402)),
    )
    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        result = process_message(session, "A durable test note.", user_id=user.id)
        entry = session.query(RawEntry).filter(RawEntry.id == result["entry_id"]).one()
        assert result["type"] == "error"
        assert entry.processed_status == "error"
        assert entry.processing_error == "Extraction failed: _ProviderStatusError"
    finally:
        session.close()


def test_retryable_provider_failure_is_queued_without_leaking_error_text(isolated_db, monkeypatch):
    from thoughtpins.db import RawEntry
    from thoughtpins.ingestion.pipeline import process_message
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user

    monkeypatch.setattr(
        "thoughtpins.ingestion.pipeline.classify_message",
        lambda text: {"type": "journal_entry", "intent": "test"},
    )
    monkeypatch.setattr(
        "thoughtpins.ingestion.pipeline.extract_from_entry",
        lambda text, local_datetime: (_ for _ in ()).throw(_ProviderStatusError(503)),
    )
    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        result = process_message(session, "A durable outage test note.", user_id=user.id)
        entry = session.query(RawEntry).filter(RawEntry.id == result["entry_id"]).one()
        assert result["type"] == "queued"
        assert entry.processed_status == "queued"
        assert "provider failure" not in (entry.processing_error or "")
    finally:
        session.close()


def test_process_message_rejects_inactive_owner(isolated_db) -> None:
    import pytest

    from thoughtpins.db import RawEntry
    from thoughtpins.ingestion.pipeline import process_message
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user

    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        user.is_active = False
        session.commit()

        with pytest.raises(ValueError, match="inactive"):
            process_message(session, "This must not be written after deletion begins.", user_id=user.id)

        assert session.query(RawEntry).filter(RawEntry.user_id == user.id).count() == 0
    finally:
        session.close()


def test_process_message_persists_action_item_due_at(isolated_db, monkeypatch):
    from datetime import timedelta

    from thoughtpins.db import ActionItem
    from thoughtpins.ingestion.pipeline import process_message
    from thoughtpins.llm import ExtractedActionItem, ExtractionResult
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user
    from thoughtpins.utils import local_today

    monkeypatch.setattr(
        "thoughtpins.ingestion.pipeline.classify_message",
        lambda text: {"type": "journal_entry", "intent": "test"},
    )
    monkeypatch.setattr(
        "thoughtpins.ingestion.pipeline.extract_from_entry",
        lambda text, local_datetime: ExtractionResult(
            action_items=[ExtractedActionItem(description="clean the apartment", due_at="tomorrow")]
        ),
    )

    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        result = process_message(session, "tomorrow remind me to clean the apartment", user_id=user.id)
        action = session.query(ActionItem).filter(ActionItem.raw_entry_id == result["entry_id"]).one()

        assert result["type"] == "journal_stored"
        assert action.description == "clean the apartment"
        assert action.due_at is not None
        assert action.due_at.date() == local_today() + timedelta(days=1)
        assert action.due_at.hour == 9
    finally:
        session.close()


def test_process_message_recovers_missing_action_due_at_from_raw_text(isolated_db, monkeypatch):
    from datetime import timedelta

    from thoughtpins.db import ActionItem
    from thoughtpins.ingestion.pipeline import process_message
    from thoughtpins.llm import ExtractedActionItem, ExtractionResult
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user
    from thoughtpins.utils import local_today

    monkeypatch.setattr(
        "thoughtpins.ingestion.pipeline.classify_message",
        lambda text: {"type": "journal_entry", "intent": "test"},
    )
    monkeypatch.setattr(
        "thoughtpins.ingestion.pipeline.extract_from_entry",
        lambda text, local_datetime: ExtractionResult(
            action_items=[ExtractedActionItem(description="clean the apartment", due_at=None)]
        ),
    )

    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        result = process_message(session, "tomorrow remind me to clean the apartment", user_id=user.id)
        action = session.query(ActionItem).filter(ActionItem.raw_entry_id == result["entry_id"]).one()

        assert action.due_at is not None
        assert action.due_at.date() == local_today() + timedelta(days=1)
        assert action.due_at.hour == 9
    finally:
        session.close()


def test_process_message_preserves_explicit_reminder_time_and_dedupes_combined_actions(
    isolated_db,
    monkeypatch,
):
    from datetime import timedelta

    from thoughtpins.db import ActionItem
    from thoughtpins.ingestion.pipeline import process_message
    from thoughtpins.llm import ExtractedActionItem, ExtractionResult
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user
    from thoughtpins.utils import local_today

    monkeypatch.setattr(
        "thoughtpins.ingestion.pipeline.classify_message",
        lambda text: {"type": "journal_entry", "intent": "test"},
    )
    monkeypatch.setattr(
        "thoughtpins.ingestion.pipeline.extract_from_entry",
        lambda text, local_datetime: ExtractionResult(
            action_items=[
                ExtractedActionItem(description="draft privacy policy checklist", due_at="tomorrow at 10am"),
                ExtractedActionItem(description="send Priya backend release notes", due_at="tomorrow at 10am"),
                ExtractedActionItem(
                    description="remind Dana to draft privacy policy checklist and send backend release notes",
                    due_at="tomorrow at 10am",
                ),
            ]
        ),
    )

    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        result = process_message(
            session,
            "tomorrow at 10am remind me to draft the checklist and send Priya release notes",
            user_id=user.id,
        )
        actions = (
            session.query(ActionItem)
            .filter(ActionItem.raw_entry_id == result["entry_id"])
            .order_by(ActionItem.description)
            .all()
        )

        assert [action.description for action in actions] == [
            "draft privacy policy checklist",
            "send Priya backend release notes",
        ]
        assert all(action.due_at is not None for action in actions)
        assert {action.due_at.date() for action in actions} == {local_today() + timedelta(days=1)}
        assert {action.due_at.hour for action in actions} == {10}
    finally:
        session.close()


def test_process_message_drops_implicit_undated_action_items_from_reflections(
    isolated_db,
    monkeypatch,
):
    from thoughtpins.db import ActionItem
    from thoughtpins.ingestion.pipeline import process_message
    from thoughtpins.llm import ExtractedActionItem, ExtractionResult
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user

    monkeypatch.setattr(
        "thoughtpins.ingestion.pipeline.classify_message",
        lambda text: {"type": "journal_entry", "intent": "test"},
    )
    monkeypatch.setattr(
        "thoughtpins.ingestion.pipeline.extract_from_entry",
        lambda text, local_datetime: ExtractionResult(
            action_items=[ExtractedActionItem(description="validate reliability before UI polish", due_at=None)]
        ),
    )

    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        result = process_message(
            session,
            "I decided reliability should come before UI polish.",
            user_id=user.id,
        )
        count = session.query(ActionItem).filter(ActionItem.raw_entry_id == result["entry_id"]).count()

        assert count == 0
    finally:
        session.close()


def test_process_message_links_expense_to_merchant_entity(isolated_db, monkeypatch):
    from thoughtpins.db import Entity, Expense
    from thoughtpins.ingestion.pipeline import process_message
    from thoughtpins.llm import ExtractedExpense, ExtractionResult
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user

    monkeypatch.setattr(
        "thoughtpins.ingestion.pipeline.classify_message",
        lambda text: {"type": "journal_entry", "intent": "test"},
    )
    monkeypatch.setattr(
        "thoughtpins.ingestion.pipeline.extract_from_entry",
        lambda text, local_datetime: ExtractionResult(
            expenses=[
                ExtractedExpense(
                    amount=18.75,
                    currency="USD",
                    merchant_or_place="Northstar Cafe",
                    reason="coffee and snacks",
                    category="food",
                )
            ]
        ),
    )

    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        result = process_message(
            session,
            "I spent $18.75 at Northstar Cafe for coffee and snacks.",
            user_id=user.id,
        )
        expense = session.query(Expense).filter(Expense.raw_entry_id == result["entry_id"]).one()
        merchant = session.query(Entity).filter(Entity.id == expense.merchant_or_place_entity_id).one()

        assert merchant.canonical_name == "Northstar Cafe"
        assert merchant.type == "place"
    finally:
        session.close()


def test_process_message_dedupes_repetitive_memory_extraction(isolated_db, monkeypatch):
    from thoughtpins.db import Memory
    from thoughtpins.ingestion.pipeline import process_message
    from thoughtpins.llm import ExtractedMemory, ExtractionResult
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_default_user

    monkeypatch.setattr(
        "thoughtpins.ingestion.pipeline.classify_message",
        lambda text: {"type": "journal_entry", "intent": "test"},
    )
    monkeypatch.setattr(
        "thoughtpins.ingestion.pipeline.extract_from_entry",
        lambda text, local_datetime: ExtractionResult(
            memories=[
                ExtractedMemory(memory_type="decision", text="Dana decided reliability should come before UI polish."),
                ExtractedMemory(memory_type="decision", text="Dana decided reliability should come before UI polish."),
                ExtractedMemory(memory_type="decision", text="Reliability should come before UI polish."),
            ]
        ),
    )

    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        result = process_message(
            session,
            "Dana decided reliability should come before UI polish. Reliability should come before UI polish.",
            user_id=user.id,
        )
        memories = session.query(Memory).filter(Memory.raw_entry_id == result["entry_id"]).all()

        assert [memory.text for memory in memories] == ["Dana decided reliability should come before UI polish."]
    finally:
        session.close()


def test_long_form_essay_classifies_as_journal_without_llm(monkeypatch):
    from thoughtpins.ingestion import classify

    def fail_llm():
        raise AssertionError("Long-form essays should not require LLM classification")

    monkeypatch.setattr(classify, "get_llm_client", fail_llm)

    text = (
        "Synthetic long essay about app readiness. "
        + "The journal app needs reliable memory-aware chat, backups, and deployment checks. " * 40
    )

    result = classify.classify_message(text)

    assert result["type"] == "journal_entry"
    assert "long-form" in result["intent"]


def test_note_style_messages_classify_as_journal_without_llm(monkeypatch):
    from thoughtpins.ingestion import classify

    def fail_llm():
        raise AssertionError("Note-style journal entries should not require LLM classification")

    monkeypatch.setattr(classify, "get_llm_client", fail_llm)

    examples = [
        "quick note from Green Bar: met Jordan and spent $12",
        "random thought: attention feels like compound interest",
        "business idea: memory layer for founders",
        "spiritual note: humility helped today",
        "TPIN_TEST: coffee chat with Maya about privacy",
    ]

    for text in examples:
        result = classify.classify_message(text)
        assert result["type"] == "journal_entry"
        assert "note-style" in result["intent"]


def test_entity_type_correction_does_not_keep_generic_concepts_as_people(monkeypatch):
    from thoughtpins.ingestion import extraction
    from thoughtpins.llm import ExtractedEntity, ExtractionResult

    class FailingLLM:
        def chat(self, *args, **kwargs):
            raise AssertionError("Heuristics should fix these without an LLM call")

    monkeypatch.setattr(extraction, "get_llm_client", lambda: FailingLLM())

    result = extraction.correct_entity_types(
        ExtractionResult(
            entities=[
                ExtractedEntity(surface_name="Jordan", type="person"),
                ExtractedEntity(surface_name="Conversation", type="Person"),
                ExtractedEntity(surface_name="The Day", type="Person"),
                ExtractedEntity(surface_name="Coworking Session", type="Person"),
                ExtractedEntity(
                    surface_name="Make The Quiet Version Work Before The Impressive Version", type="Person"
                ),
            ]
        ),
        "Jordan said my plan sounded calmer. Maya said, 'make the quiet version work before the impressive version.' The day felt cohesive.",
    )

    types = {entity.surface_name: entity.type for entity in result.entities}

    assert types["Jordan"] == "person"
    assert types["Conversation"] == "concept"
    assert types["The Day"] == "concept"
    assert types["Coworking Session"] == "event"
    assert types["Make The Quiet Version Work Before The Impressive Version"] == "concept"


def test_entity_type_correction_repairs_malformed_llm_json(monkeypatch):
    from thoughtpins.ingestion import extraction
    from thoughtpins.llm import ExtractedEntity, ExtractionResult

    class MalformedJsonLLM:
        def chat(self, *args, **kwargs):
            return '{"corrections": [{"surface_name": "Roadmap", "correct_type": "concept",},],}'

    monkeypatch.setattr(extraction, "get_llm_client", lambda: MalformedJsonLLM())

    result = extraction.correct_entity_types(
        ExtractionResult(
            entities=[
                ExtractedEntity(surface_name="Roadmap", type="person"),
            ]
        ),
        "Roadmap felt clearer after the notes were organized.",
    )

    assert result.entities[0].type == "concept"


def test_entity_type_correction_preserves_reserved_journal_owner(monkeypatch):
    from thoughtpins.ingestion import extraction
    from thoughtpins.llm import ExtractedEntity, ExtractionResult

    class FailingLLM:
        def chat(self, *args, **kwargs):
            raise AssertionError("The reserved journal owner should not require LLM review")

    monkeypatch.setattr(extraction, "get_llm_client", lambda: FailingLLM())

    result = extraction.correct_entity_types(
        ExtractionResult(
            entities=[
                ExtractedEntity(surface_name="User", canonical_guess="User", type="concept"),
            ]
        ),
        "User reflected on the day.",
    )

    assert result.entities[0].type == "person"


def test_entity_type_correction_preserves_multi_part_people_in_social_context(monkeypatch):
    from thoughtpins.ingestion import extraction
    from thoughtpins.llm import ExtractedEntity, ExtractionResult

    class FailingLLM:
        def chat(self, *args, **kwargs):
            raise AssertionError("Explicit social verbs should settle person entities locally")

    monkeypatch.setattr(extraction, "get_llm_client", lambda: FailingLLM())

    result = extraction.correct_entity_types(
        ExtractionResult(
            entities=[
                ExtractedEntity(surface_name="Load Person Seven", type="person"),
                ExtractedEntity(surface_name="Mary Jane Watson", type="person"),
            ]
        ),
        "I met Load Person Seven at Atlas Cafe. Mary Jane Watson joined us later.",
    )

    assert [entity.type for entity in result.entities] == ["person", "person"]


def test_entity_storage_normalizes_bad_llm_types(isolated_db):
    from thoughtpins.db import Entity
    from thoughtpins.ingestion.entity_resolution import create_or_get_entity
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram

    session = get_session()
    try:
        user = get_or_create_user_for_telegram("entity-normalize-chat", session=session)
        create_or_get_entity(
            session,
            "Jordan",
            "Jordan",
            "Person",
            raw_text="Jordan said the calmer plan sounded better.",
            user_id=user.id,
        )
        create_or_get_entity(
            session,
            "The Day",
            "The Day",
            "person",
            raw_text="The day felt cohesive and oddly quiet.",
            user_id=user.id,
        )
        create_or_get_entity(
            session,
            "Make The Quiet Version Work Before The Impressive Version",
            "Make The Quiet Version Work Before The Impressive Version",
            "person",
            raw_text="Maya said, 'make the quiet version work before the impressive version.'",
            user_id=user.id,
        )
        create_or_get_entity(
            session,
            "Coffee Chat",
            "Coffee Chat",
            "person",
            raw_text="Had a coffee chat with Maya about privacy.",
            user_id=user.id,
        )
        create_or_get_entity(
            session,
            "Humility",
            "Humility",
            "person",
            raw_text="Humility helped the day feel cleaner.",
            user_id=user.id,
        )
        create_or_get_entity(
            session,
            "Fear",
            "Fear",
            "person",
            raw_text="Fear was present but did not need to run the whole day.",
            user_id=user.id,
        )
        session.commit()

        entities = {e.canonical_name: e.type for e in session.query(Entity).filter(Entity.user_id == user.id).all()}
        assert entities["Jordan"] == "person"
        assert entities["The Day"] == "concept"
        assert entities["Make The Quiet Version Work Before The Impressive Version"] == "concept"
        assert entities["Coffee Chat"] == "event"
        assert entities["Humility"] == "concept"
        assert entities["Fear"] == "concept"
    finally:
        session.close()


def test_memory_subject_storage_does_not_force_generic_subjects_to_people(isolated_db):
    from thoughtpins.db import Entity, RawEntry
    from thoughtpins.ingestion.pipeline import _store_extraction
    from thoughtpins.llm import ExtractedMemory, ExtractionResult
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram
    from thoughtpins.utils import hash_text, local_today

    session = get_session()
    try:
        user = get_or_create_user_for_telegram("memory-subject-normalize-chat", session=session)
        raw_text = "The day felt cohesive because I kept returning to the quieter version."
        raw = RawEntry(
            user_id=user.id,
            raw_text=raw_text,
            content_hash=hash_text(raw_text),
            local_date=local_today(),
            processed_status="processing",
        )
        session.add(raw)
        session.flush()

        _store_extraction(
            session,
            raw,
            ExtractionResult(
                memories=[
                    ExtractedMemory(
                        memory_type="thought",
                        subject="The Day",
                        predicate="felt",
                        text="The day felt cohesive.",
                    )
                ]
            ),
            local_today(),
            raw_text=raw_text,
        )
        session.commit()

        day = (
            session.query(Entity)
            .filter(
                Entity.user_id == user.id,
                Entity.canonical_name == "The Day",
            )
            .one()
        )
        assert day.type == "concept"
    finally:
        session.close()


def test_entity_resolution_skips_llm_for_stopword_only_overlap(isolated_db, monkeypatch):
    from thoughtpins.ingestion import entity_resolution
    from thoughtpins.ingestion.entity_resolution import create_or_get_entity
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram

    def fail_batch_resolve(*args, **kwargs):
        raise AssertionError("Unrelated concept names should not call semantic LLM resolution")

    monkeypatch.setattr(entity_resolution, "_batch_semantic_resolve", fail_batch_resolve)

    session = get_session()
    try:
        user = get_or_create_user_for_telegram("entity-resolution-stopword-chat", session=session)
        create_or_get_entity(
            session,
            "The Day",
            "The Day",
            "concept",
            raw_text="The day felt cohesive.",
            user_id=user.id,
        )
        quote = create_or_get_entity(
            session,
            "Make The Quiet Version Work Before The Impressive Version",
            "Make The Quiet Version Work Before The Impressive Version",
            "concept",
            raw_text="Maya said to make the quiet version work before the impressive version.",
            user_id=user.id,
        )

        assert quote.canonical_name == "Make The Quiet Version Work Before The Impressive Version"
        assert quote.type == "concept"
    finally:
        session.close()


def test_due_telegram_reminders_are_sent_once(isolated_db, monkeypatch):
    from datetime import timedelta
    from pathlib import Path
    from uuid import uuid4

    from thoughtpins.bot import reminders
    from thoughtpins.db import ActionItem, RawEntry
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram
    from thoughtpins.utils import hash_text, local_now

    sent_path = Path(".tmp") / "test-reminders" / f"{uuid4().hex}.json"
    monkeypatch.setattr(reminders, "_sent_path", lambda: sent_path)

    session = get_session()
    try:
        user = get_or_create_user_for_telegram("chat-1", session=session)
        raw = RawEntry(
            user_id=user.id,
            raw_text="tomorrow remind me to clean",
            content_hash=hash_text("tomorrow remind me to clean"),
            telegram_chat_id="chat-1",
            processed_status="completed",
        )
        session.add(raw)
        session.flush()
        action = ActionItem(
            user_id=user.id,
            raw_entry_id=raw.id,
            description="clean the apartment",
            due_at=local_now().replace(tzinfo=None) - timedelta(minutes=1),
            status="open",
        )
        session.add(action)
        session.commit()

        due = reminders.find_due_telegram_reminders(session)
        assert [item[0].id for item in due] == [action.id]
        assert "clean the apartment" in reminders.format_reminder(action)

        reminders._save_sent_ids({action.id})
        assert reminders.find_due_telegram_reminders(session) == []
    finally:
        session.close()
