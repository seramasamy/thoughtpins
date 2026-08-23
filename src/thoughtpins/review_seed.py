"""Seed a safe closed-beta review account with representative data.

The data in this module is intentionally fictional and non-personal. It gives
App Review, Play review, and internal closed-beta testers enough material to
exercise chat, memory cards, library, entries, jobs, export, and deletion without
using founder/private data or spending LLM credits.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from thoughtpins.audit import record_audit_event
from thoughtpins.auth import hash_password
from thoughtpins.config import config
from thoughtpins.data_lifecycle import delete_user_data, export_user_data
from thoughtpins.db import (
    ActionItem,
    AppDevice,
    AuditLog,
    ChatConversation,
    ChatMessage,
    DocumentChunk,
    DocumentSource,
    Entity,
    EntityMention,
    Event,
    EventParticipant,
    Expense,
    IngestionJob,
    Memory,
    RawEntry,
    Relationship,
    User,
)
from thoughtpins.invites import create_invite_code, invite_required, redeem
from thoughtpins.store import get_session
from thoughtpins.users import get_user_by_email, register_user
from thoughtpins.utils import hash_text

REVIEW_EMAIL_DEFAULT = "review@thoughtpins.com"
REVIEW_SOURCE = "review_seed"
LEGAL_VERSION = config.LEGAL_DOCUMENT_VERSION


@dataclass(frozen=True)
class ReviewSeedResult:
    user_id: str
    email: str
    reset_existing_user: bool
    entries: int
    entities: int
    memories: int
    relationships: int
    events: int
    documents: int
    chunks: int
    chat_messages: int
    jobs: int
    devices: int
    audit_logs: int
    export_tables: int
    invite_admitted: bool = False
    vault_path: str | None = None
    vault_files: int | None = None
    vault_validation_errors: int | None = None
    vault_zip_path: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def seed_review_account(
    *,
    email: str = REVIEW_EMAIL_DEFAULT,
    password: str,
    reset: bool = True,
    allow_production: bool = False,
    export_vault: bool = False,
    package_vault_zip: bool = False,
    session: Session | None = None,
) -> ReviewSeedResult:
    """Create or replace the safe review account and representative fixture data."""
    normalized_email = _normalize_email(email)
    if len(password) < 12:
        raise ValueError("Review password must be at least 12 characters.")
    if config.is_production() and not allow_production:
        raise RuntimeError("Refusing to seed review data in production without allow_production=True.")

    owns_session = session is None
    session = session or get_session()
    try:
        reset_existing_user = _prepare_review_user_slot(session, normalized_email, reset=reset)
        user = register_user(
            email=normalized_email,
            display_name="Thought Pins Review User",
            password_hash=hash_password(password),
            session=session,
            bypass_system_lock=True,
        )
        user.preferences_json = _review_preferences()
        session.commit()
        session.refresh(user)

        invite_admitted = _admit_review_user(session, user)
        session.refresh(user)

        rows = _seed_review_rows(session, user)
        export_payload = export_user_data(session, user.id)
        vault_info = _export_review_vault(session, user.id, package_zip=package_vault_zip) if export_vault else {}
        return ReviewSeedResult(
            user_id=user.id,
            email=normalized_email,
            reset_existing_user=reset_existing_user,
            entries=rows["entries"],
            entities=rows["entities"],
            memories=rows["memories"],
            relationships=rows["relationships"],
            events=rows["events"],
            documents=rows["documents"],
            chunks=rows["chunks"],
            chat_messages=rows["chat_messages"],
            jobs=rows["jobs"],
            devices=rows["devices"],
            audit_logs=rows["audit_logs"],
            export_tables=len(export_payload.get("tables", {})),
            invite_admitted=invite_admitted,
            vault_path=vault_info.get("vault_path"),
            vault_files=vault_info.get("vault_files"),
            vault_validation_errors=vault_info.get("vault_validation_errors"),
            vault_zip_path=vault_info.get("vault_zip_path"),
        )
    finally:
        if owns_session:
            session.close()


def _admit_review_user(session: Session, user: User) -> bool:
    """Let the review account past the closed-beta invite gate.

    Production runs `INVITE_ONLY=true` so the public site stays closed, and
    nothing in this seed used to touch that. The demo account therefore signed
    in correctly and then met the invite wall — App Review would have seen a
    gate instead of the product, which is what a Guideline 2.1 "unable to
    review" rejection is made of.

    Admission goes through a real single-use `InviteCode`, redeemed the way any
    invitation is. The alternative — a flag that skips the gate — would be a
    second admission path present for every account, permanently, so that one
    reviewer could sign in. The plaintext code is deliberately discarded: it has
    already been consumed and is of no use to anyone afterwards.
    """
    if not invite_required():
        return False
    _record, code = create_invite_code(session, label="app-review", max_uses=1)
    redeem(session, user, code)
    return True


def _prepare_review_user_slot(session: Session, email: str, *, reset: bool) -> bool:
    existing = get_user_by_email(email, session=session)
    if not existing:
        return False
    if not reset:
        raise ValueError(f"Review user {email} already exists. Use reset=True to replace it.")
    delete_user_data(session, existing.id)
    return True


def _review_preferences() -> dict[str, Any]:
    now = _utcnow().isoformat()
    return {
        "app_preferences": {
            "preferred_name": "Review",
            "timezone": "America/New_York",
            "notifications_enabled": False,
            "weekly_digest_enabled": False,
            "product_updates_enabled": False,
            "private_entries_in_ask": False,
            "response_style": "friendly",
        },
        "email_verification": {"verified": True, "source": "review_seed"},
        "legal_acceptances": {
            "privacy": {"version": LEGAL_VERSION, "accepted_at_utc": now},
            "terms": {"version": LEGAL_VERSION, "accepted_at_utc": now},
            "ai_disclosure": {"version": LEGAL_VERSION, "accepted_at_utc": now},
        },
    }


def _seed_review_rows(session: Session, user: User) -> dict[str, int]:
    now = datetime(2026, 7, 1, 14, 30)
    day = now.date()

    journal = RawEntry(
        user_id=user.id,
        created_at_utc=now,
        local_date=day,
        local_time="10:30",
        source=REVIEW_SOURCE,
        raw_text=(
            "Closed beta review note: I met Maya at Atlas Cafe. She noticed the copper lantern "
            "above the window and said it would make a good recall anchor for the Northstar Memory project. "
            "We agreed to test whether small sensory details improve later memory search."
        ),
        content_hash=hash_text(f"review-journal-{user.id}"),
        sensitivity="personal",
        processed_status="completed",
    )
    document_entry = RawEntry(
        user_id=user.id,
        created_at_utc=now + timedelta(minutes=5),
        local_date=day,
        local_time="10:35",
        source="library_doc",
        raw_text=(
            "Library source: Review Article - Attention and Recall\n\n"
            "This fictional review article explains how distinct sensory anchors, deliberate reflection, "
            "and source provenance improve long-term memory retrieval."
        ),
        content_hash=hash_text(f"review-document-entry-{user.id}"),
        sensitivity="personal",
        processed_status="completed",
    )
    session.add_all([journal, document_entry])
    session.flush()

    entities = {
        "user": Entity(user_id=user.id, type="person", canonical_name="Review User", aliases_json=["user"]),
        "maya": Entity(user_id=user.id, type="person", canonical_name="Maya", aliases_json=["Maya from Atlas Cafe"]),
        "atlas": Entity(user_id=user.id, type="place", canonical_name="Atlas Cafe"),
        "lantern": Entity(
            user_id=user.id, type="thing", canonical_name="Copper Lantern", aliases_json=["lantern anchor"]
        ),
        "northstar": Entity(user_id=user.id, type="project", canonical_name="Northstar Memory"),
        "attention": Entity(user_id=user.id, type="concept", canonical_name="Attention Anchors"),
    }
    session.add_all(entities.values())
    session.flush()

    mentions = [
        EntityMention(user_id=user.id, raw_entry_id=journal.id, entity_id=entities["maya"].id, surface_text="Maya"),
        EntityMention(
            user_id=user.id, raw_entry_id=journal.id, entity_id=entities["atlas"].id, surface_text="Atlas Cafe"
        ),
        EntityMention(
            user_id=user.id, raw_entry_id=journal.id, entity_id=entities["lantern"].id, surface_text="copper lantern"
        ),
        EntityMention(
            user_id=user.id,
            raw_entry_id=journal.id,
            entity_id=entities["northstar"].id,
            surface_text="Northstar Memory",
        ),
        EntityMention(
            user_id=user.id, raw_entry_id=journal.id, entity_id=entities["attention"].id, surface_text="recall anchor"
        ),
    ]
    session.add_all(mentions)

    memories = [
        Memory(
            user_id=user.id,
            raw_entry_id=journal.id,
            memory_type="social",
            subject_entity_id=entities["maya"].id,
            object_entity_id=entities["lantern"].id,
            predicate="noticed",
            text="Maya noticed the copper lantern at Atlas Cafe and framed it as a recall anchor.",
            structured_json={"review_seed": True, "source_kind": "journal"},
            local_date=day,
            confidence="observed_by_user",
            source_provenance=f"raw_entry:{journal.id}",
            created_at_utc=journal.created_at_utc,
        ),
        Memory(
            user_id=user.id,
            raw_entry_id=journal.id,
            memory_type="project",
            subject_entity_id=entities["northstar"].id,
            object_entity_id=entities["attention"].id,
            predicate="tests",
            text="Northstar Memory is testing whether sensory anchors improve later recall search.",
            structured_json={"review_seed": True, "source_kind": "journal"},
            local_date=day,
            confidence="observed_by_user",
            source_provenance=f"raw_entry:{journal.id}",
            created_at_utc=journal.created_at_utc,
        ),
        Memory(
            user_id=user.id,
            raw_entry_id=document_entry.id,
            memory_type="source_summary",
            subject_entity_id=entities["attention"].id,
            text=(
                "Source saved: Review Article - Attention and Recall. Type: article. Status: processed. "
                "Summary: distinct sensory anchors and source provenance improve long-term retrieval."
            ),
            structured_json={"review_seed": True, "source_kind": "document"},
            local_date=day,
            confidence="observed_by_user",
            source_provenance="document:pending",
            created_at_utc=document_entry.created_at_utc,
        ),
    ]
    session.add_all(memories)

    relationships = [
        Relationship(
            user_id=user.id,
            source_entity_id=entities["user"].id,
            target_entity_id=entities["maya"].id,
            relation_type="knows",
            raw_entry_id=journal.id,
            weight=3.0,
            confidence="observed_by_user",
            first_seen_at=journal.created_at_utc,
            last_seen_at=journal.created_at_utc,
            evidence_count=1,
        ),
        Relationship(
            user_id=user.id,
            source_entity_id=entities["maya"].id,
            target_entity_id=entities["atlas"].id,
            relation_type="met_at",
            raw_entry_id=journal.id,
            weight=2.0,
            confidence="observed_by_user",
            first_seen_at=journal.created_at_utc,
            last_seen_at=journal.created_at_utc,
            evidence_count=1,
        ),
        Relationship(
            user_id=user.id,
            source_entity_id=entities["user"].id,
            target_entity_id=entities["northstar"].id,
            relation_type="works_on",
            raw_entry_id=journal.id,
            weight=2.5,
            confidence="observed_by_user",
            first_seen_at=journal.created_at_utc,
            last_seen_at=journal.created_at_utc,
            evidence_count=1,
        ),
    ]
    session.add_all(relationships)

    event = Event(
        user_id=user.id,
        name="Review Coffee Chat With Maya",
        event_type="coffee_chat",
        local_date=day,
        place_entity_id=entities["atlas"].id,
        summary="Maya and the review user discussed sensory anchors for Northstar Memory at Atlas Cafe.",
        source_raw_entry_id=journal.id,
    )
    session.add(event)
    session.flush()
    session.add_all(
        [
            EventParticipant(user_id=user.id, event_id=event.id, entity_id=entities["user"].id, role="self"),
            EventParticipant(user_id=user.id, event_id=event.id, entity_id=entities["maya"].id, role="attendee"),
        ]
    )

    session.add(
        ActionItem(
            user_id=user.id,
            raw_entry_id=journal.id,
            description="Review seed: compare memory cards after adding a document source.",
            due_at=now + timedelta(days=1),
            status="open",
            sensitivity="personal",
        )
    )
    session.add(
        Expense(
            user_id=user.id,
            raw_entry_id=journal.id,
            amount=18.75,
            currency="USD",
            merchant_or_place_entity_id=entities["atlas"].id,
            reason="Coffee and pastry during review seed conversation",
            category="food",
        )
    )

    document_text = (
        "Attention and Recall is a fictional public review note for Thought Pins app review. "
        "It says that memory works better when a saved thought keeps its source, a concrete sensory detail, "
        "and a link to the people, places, projects, and concepts involved. The copper lantern is the example detail."
    )
    document = DocumentSource(
        user_id=user.id,
        raw_entry_id=document_entry.id,
        source_type="article",
        title="Review Article - Attention and Recall",
        author="Thought Pins Demo",
        original_url="https://thoughtpins.com/demo/attention-and-recall",
        source_url="https://thoughtpins.com/demo/attention-and-recall",
        canonical_url="https://thoughtpins.com/demo/attention-and-recall",
        source_domain="thoughtpins.com",
        access_method="user_paste",
        rights_basis="user_provided",
        fetch_status="processed",
        paywall_detected=False,
        retrieval_quality_score=1.0,
        content_hash=hash_text(f"review-document-{user.id}"),
        raw_text=document_text,
        summary="A safe fictional article about source provenance and sensory anchors in memory retrieval.",
        status="processed",
        sensitivity="personal",
        created_at_utc=document_entry.created_at_utc,
        local_date=day,
        metadata_json={
            "review_seed": True,
            "reading_analysis": {
                "publisher": "Thought Pins",
                "topics": ["memory", "source provenance", "attention"],
                "key_concepts": ["sensory anchors", "provenance", "memory cards"],
                "word_count": len(document_text.split()),
            },
        },
    )
    session.add(document)
    session.flush()
    session.add(
        DocumentChunk(
            user_id=user.id,
            document_id=document.id,
            chunk_index=0,
            text=document_text,
            char_start=0,
            char_end=len(document_text),
            token_count=max(1, len(document_text) // 4),
            section_heading="Review note",
            metadata_json={"review_seed": True},
        )
    )
    for memory in memories:
        if memory.source_provenance == "document:pending":
            memory.source_provenance = f"document:{document.id}"
            memory.structured_json = (memory.structured_json or {}) | {
                "document_id": document.id,
                "title": document.title,
            }

    conversation = ChatConversation(
        user_id=user.id,
        conversation_key="web:main",
        surface="web",
        title="main",
        created_at_utc=now,
        updated_at_utc=now + timedelta(minutes=8),
        last_message_at_utc=now + timedelta(minutes=8),
        metadata_json={"review_seed": True},
    )
    session.add(conversation)
    session.flush()
    session.add_all(
        [
            ChatMessage(
                user_id=user.id,
                conversation_id=conversation.id,
                role="user",
                text="What should I remember about Maya and the copper lantern?",
                route_type="chat",
                status="completed",
                created_at_utc=now + timedelta(minutes=7),
                metadata_json={"review_seed": True},
            ),
            ChatMessage(
                user_id=user.id,
                conversation_id=conversation.id,
                role="assistant",
                text="Maya noticed the copper lantern at Atlas Cafe and used it as the sensory anchor for the Northstar Memory recall test.",
                route_type="chat",
                status="completed",
                created_at_utc=now + timedelta(minutes=8),
                metadata_json={"review_seed": True},
            ),
        ]
    )

    session.add(
        IngestionJob(
            user_id=user.id,
            status="completed",
            source=REVIEW_SOURCE,
            raw_text=journal.raw_text,
            entry_id=journal.id,
            created_at_utc=now,
            started_at_utc=now,
            finished_at_utc=now + timedelta(seconds=2),
            metadata_json={"review_seed": True},
        )
    )
    session.add(
        AppDevice(
            user_id=user.id,
            installation_id="review-web-installation",
            platform="web",
            device_name="Review Browser",
            app_version=config.API_VERSION,
            build_number="review",
            os_version="web",
            locale="en-US",
            timezone="America/New_York",
            notifications_enabled=False,
            metadata_json={"review_seed": True},
        )
    )
    record_audit_event(session, user_id=user.id, action="review.seed", metadata={"source": REVIEW_SOURCE})
    session.commit()

    return {
        "entries": session.query(RawEntry).filter(RawEntry.user_id == user.id).count(),
        "entities": session.query(Entity).filter(Entity.user_id == user.id).count(),
        "memories": session.query(Memory).filter(Memory.user_id == user.id).count(),
        "relationships": session.query(Relationship).filter(Relationship.user_id == user.id).count(),
        "events": session.query(Event).filter(Event.user_id == user.id).count(),
        "documents": session.query(DocumentSource).filter(DocumentSource.user_id == user.id).count(),
        "chunks": session.query(DocumentChunk).filter(DocumentChunk.user_id == user.id).count(),
        "chat_messages": session.query(ChatMessage).filter(ChatMessage.user_id == user.id).count(),
        "jobs": session.query(IngestionJob).filter(IngestionJob.user_id == user.id).count(),
        "devices": session.query(AppDevice).filter(AppDevice.user_id == user.id).count(),
        "audit_logs": session.query(AuditLog).filter(AuditLog.user_id == user.id).count(),
    }


def _export_review_vault(session: Session, user_id: str, *, package_zip: bool) -> dict[str, Any]:
    from thoughtpins.vault.exporter import VaultExporter

    exporter = VaultExporter(session, user_id=user_id)
    stats = exporter.export_all(clean=True, validate=True, package_zip=package_zip, obsidian_defaults=True)
    payload: dict[str, Any] = {
        "vault_path": str(exporter._vault),
        "vault_files": int(stats.get("vault_files") or 0),
        "vault_validation_errors": int(stats.get("validation_errors") or 0),
    }
    if stats.get("zip_path"):
        payload["vault_zip_path"] = str(stats["zip_path"])
    return payload


def _normalize_email(email: str) -> str:
    normalized = (email or "").strip().lower()
    if not normalized or "@" not in normalized:
        raise ValueError("Review email must be a valid email address.")
    return normalized


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
