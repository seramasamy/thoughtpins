"""Editing a turn discards the branch below it — without destroying what it wrote.

In a chat product an edit simply throws away the replies that followed. A
journal is different: one of those turns may have saved an entry, extracted
memories, or stored a source. Deleting that because someone fixed a typo would
be destroying writing the user never asked to lose, and silently orphaning it
is not much better. So retired turns are marked, and anything they saved is
reported back for the interface to raise explicitly.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from thoughtpins.chat.store import attribute_supersede, list_messages, prompt_history, supersede_from
from thoughtpins.db import Base, ChatConversation, ChatMessage, RawEntry, User
from thoughtpins.store import get_engine, get_session

CONVERSATION = "conv1"
OWNER = "user-a"
STRANGER = "user-b"


@pytest.fixture
def session(monkeypatch, tmp_path):
    from thoughtpins.config import Config, config

    url = f"sqlite:///{(tmp_path / 'chat.sqlite3').as_posix()}"
    for target in (config, Config):
        monkeypatch.setattr(target, "DATABASE_URL", url)
    import thoughtpins.store as store_module

    monkeypatch.setattr(store_module, "_engine", None, raising=False)
    monkeypatch.setattr(store_module, "_SessionLocal", None, raising=False)
    Base.metadata.create_all(get_engine())
    db = get_session()
    for user_id in (OWNER, STRANGER):
        db.add(User(id=user_id, email=f"{user_id}@example.test"))
    db.add(ChatConversation(id=CONVERSATION, user_id=OWNER, conversation_key="main", surface="web"))
    db.commit()
    yield db
    db.close()


def add(db, *, role: str, text: str, minute: int, user_id: str = OWNER, entry_id: str | None = None) -> ChatMessage:
    row = ChatMessage(
        id=f"m{minute}{role[0]}",
        user_id=user_id,
        conversation_id=CONVERSATION,
        role=role,
        text=text,
        raw_entry_id=entry_id,
        created_at_utc=datetime(2026, 8, 1, 12, minute, tzinfo=UTC).replace(tzinfo=None),
    )
    db.add(row)
    db.commit()
    return row


def transcript(db) -> list[str]:
    rows, _, _ = list_messages(db, user_id=OWNER, conversation_id=CONVERSATION, page=1, limit=50)
    return [row.text for row in rows]


# ------------------------------------------------------------------ the edit


def test_the_edited_turn_and_everything_after_it_leave_the_transcript(session):
    add(session, role="user", text="what did I decide", minute=1)
    target = add(session, role="user", text="about the festival", minute=2)
    add(session, role="assistant", text="you decided to go", minute=3)

    retired, _ = supersede_from(session, user_id=OWNER, conversation_id=CONVERSATION, message_id=target.id)
    session.commit()

    assert {row.id for row in retired} == {target.id, "m3a"}
    assert transcript(session) == ["what did I decide"]


def test_turns_before_the_edit_are_untouched(session):
    keep = add(session, role="user", text="earlier context", minute=1)
    target = add(session, role="user", text="the mistake", minute=2)

    supersede_from(session, user_id=OWNER, conversation_id=CONVERSATION, message_id=target.id)
    session.commit()

    assert keep.superseded_at_utc is None
    assert transcript(session) == ["earlier context"]


def test_the_model_stops_seeing_the_discarded_branch(session):
    """Otherwise it answers the edited question while reading the old replies."""
    add(session, role="user", text="keep me", minute=1)
    target = add(session, role="user", text="drop me", minute=2)
    add(session, role="assistant", text="reply to the dropped turn", minute=3)

    supersede_from(session, user_id=OWNER, conversation_id=CONVERSATION, message_id=target.id)
    session.commit()

    assert [turn["content"] for turn in prompt_history(session, user_id=OWNER, conversation_id=CONVERSATION)] == [
        "keep me"
    ]


# ------------------------------------------------------ what the turn wrote


def test_a_journal_entry_the_retired_turn_saved_is_reported_not_deleted(session):
    """The whole reason this is not a plain delete."""
    session.add(
        RawEntry(
            id="entry-77",
            user_id=OWNER,
            raw_text="today I quit my job",
            content_hash="deadbeef",
            local_date=datetime(2026, 8, 1).date(),
            source="chat",
        )
    )
    session.commit()
    target = add(session, role="user", text="today I quit my job", minute=1, entry_id="entry-77")
    add(session, role="assistant", text="saved", minute=2)

    retired, orphaned = supersede_from(session, user_id=OWNER, conversation_id=CONVERSATION, message_id=target.id)
    session.commit()

    assert orphaned == ["entry-77"], "the saved entry must be surfaced, not silently dropped"
    assert session.get(ChatMessage, target.id) is not None, "history was destroyed"
    assert retired[0].superseded_at_utc is not None


def test_a_turn_that_saved_nothing_reports_nothing(session):
    target = add(session, role="user", text="just chatting", minute=1)
    _, orphaned = supersede_from(session, user_id=OWNER, conversation_id=CONVERSATION, message_id=target.id)
    assert orphaned == []


def test_retired_turns_point_at_their_replacement(session):
    target = add(session, role="user", text="original", minute=1)
    retired, _ = supersede_from(session, user_id=OWNER, conversation_id=CONVERSATION, message_id=target.id)
    attribute_supersede(retired, replacement_id="m9u")
    session.commit()
    assert session.get(ChatMessage, target.id).superseded_by_message_id == "m9u"


# --------------------------------------------------------------- refusals


def test_another_users_message_cannot_be_edited(session):
    """The identifier is client-supplied; ownership is not."""
    add(session, role="user", text="mine", minute=1)
    theirs = ChatMessage(
        id="m9u",
        user_id=STRANGER,
        conversation_id=CONVERSATION,
        role="user",
        text="theirs",
        created_at_utc=datetime(2026, 8, 1, 12, 9),
    )
    session.add(theirs)
    session.commit()

    retired, orphaned = supersede_from(session, user_id=OWNER, conversation_id=CONVERSATION, message_id="m9u")
    session.commit()

    assert (retired, orphaned) == ([], [])
    assert session.get(ChatMessage, "m9u").superseded_at_utc is None


def test_an_assistant_turn_cannot_be_edited(session):
    """You edit what you said, not what you were told."""
    add(session, role="user", text="mine", minute=1)
    reply = add(session, role="assistant", text="the answer", minute=2)
    retired, _ = supersede_from(session, user_id=OWNER, conversation_id=CONVERSATION, message_id=reply.id)
    assert retired == []


def test_an_unknown_id_is_a_no_op_not_an_error(session):
    add(session, role="user", text="mine", minute=1)
    assert supersede_from(session, user_id=OWNER, conversation_id=CONVERSATION, message_id="nope") == ([], [])
    assert transcript(session) == ["mine"]


def test_a_turn_cannot_be_retired_twice(session):
    target = add(session, role="user", text="original", minute=1)
    supersede_from(session, user_id=OWNER, conversation_id=CONVERSATION, message_id=target.id)
    session.commit()
    assert supersede_from(session, user_id=OWNER, conversation_id=CONVERSATION, message_id=target.id) == ([], [])


def test_editing_does_not_reach_into_another_conversation(session):
    other = ChatConversation(id="conv2", user_id=OWNER, conversation_key="other", surface="web")
    session.add(other)
    session.add(
        ChatMessage(
            id="m5u",
            user_id=OWNER,
            conversation_id="conv2",
            role="user",
            text="elsewhere",
            created_at_utc=datetime(2026, 8, 1, 12, 5),
        )
    )
    target = add(session, role="user", text="here", minute=1)
    session.commit()

    supersede_from(session, user_id=OWNER, conversation_id=CONVERSATION, message_id=target.id)
    session.commit()

    assert session.get(ChatMessage, "m5u").superseded_at_utc is None, "an edit crossed conversations"


def test_ties_on_timestamp_are_broken_deterministically(session):
    """Two turns written in the same instant must still order stably, or an
    edit could retire a message it was meant to keep."""
    stamp = datetime(2026, 8, 1, 12, 0)
    for suffix in ("a", "b", "c"):
        session.add(
            ChatMessage(
                id=f"m0{suffix}",
                user_id=OWNER,
                conversation_id=CONVERSATION,
                role="user",
                text=suffix,
                created_at_utc=stamp,
            )
        )
    session.commit()

    retired, _ = supersede_from(session, user_id=OWNER, conversation_id=CONVERSATION, message_id="m0b")
    session.commit()
    assert {row.id for row in retired} == {"m0b", "m0c"}
    assert transcript(session) == ["a"]


def test_an_old_turn_is_not_retired_by_a_later_edit(session):
    add(session, role="user", text="first", minute=1)
    add(session, role="user", text="second", minute=2)
    target = add(session, role="user", text="third", minute=3)
    supersede_from(session, user_id=OWNER, conversation_id=CONVERSATION, message_id=target.id)
    session.commit()
    assert transcript(session) == ["first", "second"]


def test_a_conversation_with_only_the_edited_turn_empties_cleanly(session):
    target = add(session, role="user", text="only", minute=1)
    supersede_from(session, user_id=OWNER, conversation_id=CONVERSATION, message_id=target.id)
    session.commit()
    assert transcript(session) == []
    assert prompt_history(session, user_id=OWNER, conversation_id=CONVERSATION) == []


def test_time_moves_forward_when_a_turn_is_retired(session):
    before = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
    target = add(session, role="user", text="original", minute=1)
    retired, _ = supersede_from(session, user_id=OWNER, conversation_id=CONVERSATION, message_id=target.id)
    session.commit()
    assert retired[0].superseded_at_utc >= before
