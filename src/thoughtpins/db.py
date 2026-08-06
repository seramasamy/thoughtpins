"""SQLAlchemy ORM models for Thought Pins' relational schema."""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from thoughtpins.db_base import Base, _new_id, _utcnow


class User(Base):
    __tablename__ = "users"

    id = Column(String(32), primary_key=True, default=_new_id)
    email = Column(String(255), unique=True, nullable=True, index=True)
    phone = Column(String(32), unique=True, nullable=True)
    display_name = Column(String(128), nullable=True)
    password_hash = Column(String(255), nullable=True)
    api_key = Column(String(64), unique=True, nullable=False, default=_new_id)
    telegram_chat_id = Column(String(64), nullable=True, index=True)
    is_active = Column(Boolean, default=True, index=True)
    is_admin = Column(Boolean, default=False, index=True)
    created_at_utc = Column(DateTime, default=_utcnow)
    last_login_utc = Column(DateTime, nullable=True)
    deleted_at_utc = Column(DateTime, nullable=True)
    auth_method = Column(String(32), default="api_key")
    two_factor_enabled = Column(Boolean, default=False)
    two_factor_secret = Column(String(64), nullable=True)
    # Private-launch admission. Null means the account exists but has not been
    # let in yet: registration still succeeds and the details are kept, the
    # product simply stays closed until a code is redeemed.
    invite_code_id = Column(String(32), nullable=True, index=True)
    invite_redeemed_at_utc = Column(DateTime, nullable=True)
    preferences_json = Column(JSON, default=dict)

    raw_entries = relationship("RawEntry", back_populates="user", cascade="all, delete-orphan")
    entities = relationship("Entity", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("AuthSession", back_populates="user", cascade="all, delete-orphan")
    oauth_credentials = relationship("OAuthCredential", back_populates="user", cascade="all, delete-orphan")
    ingestion_jobs = relationship("IngestionJob", back_populates="user", cascade="all, delete-orphan")
    vault_import_sessions = relationship("VaultImportSession", back_populates="user", cascade="all, delete-orphan")
    chat_conversations = relationship("ChatConversation", back_populates="user", cascade="all, delete-orphan")
    chat_messages = relationship("ChatMessage", back_populates="user", cascade="all, delete-orphan")
    pending_chat_actions = relationship("PendingChatAction", back_populates="user", cascade="all, delete-orphan")
    safety_reports = relationship("SafetyReport", back_populates="user", cascade="all, delete-orphan")
    idempotency_records = relationship("ApiIdempotencyRecord", back_populates="user", cascade="all, delete-orphan")
    voice_assets = relationship("VoiceAsset", back_populates="user", cascade="all, delete-orphan")
    llm_usage_events = relationship("LlmUsageEvent", back_populates="user", cascade="all, delete-orphan")


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (Index("ix_auth_sessions_user_expires", "user_id", "expires_at_utc"),)

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    refresh_token_hash = Column(String(128), nullable=False, unique=True, index=True)
    created_at_utc = Column(DateTime, default=_utcnow)
    expires_at_utc = Column(DateTime, nullable=False, index=True)
    revoked_at_utc = Column(DateTime, nullable=True)
    replaced_by_session_id = Column(String(32), nullable=True)
    user_agent = Column(String(255), nullable=True)
    ip_address = Column(String(64), nullable=True)

    user = relationship("User", back_populates="sessions")


class OAuthCredential(Base):
    """Provider identity link and revocable credential metadata.

    Provider subjects are stored as hashes because the original opaque value is
    only needed while verifying a login. Refresh credentials are encrypted and
    never included in user exports.
    """

    __tablename__ = "oauth_credentials"
    __table_args__ = (
        Index(
            "ix_oauth_credentials_provider_subject",
            "provider",
            "provider_subject_hash",
            unique=True,
        ),
        Index("ix_oauth_credentials_user_provider", "user_id", "provider", unique=True),
    )

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    provider = Column(String(32), nullable=False)
    provider_subject_hash = Column(String(64), nullable=False)
    client_id = Column(String(255), nullable=True)
    refresh_token_encrypted = Column(Text, nullable=True)
    created_at_utc = Column(DateTime, default=_utcnow, nullable=False)
    updated_at_utc = Column(DateTime, default=_utcnow, nullable=False)
    last_used_at_utc = Column(DateTime, default=_utcnow, nullable=False)
    revoked_at_utc = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="oauth_credentials")


class VoiceAsset(Base):
    """Encrypted, explicitly retained voice-note media owned by one user."""

    __tablename__ = "voice_assets"
    __table_args__ = (
        Index("ix_voice_assets_user_created", "user_id", "created_at_utc"),
        Index("ix_voice_assets_user_entry", "user_id", "raw_entry_id"),
        CheckConstraint("byte_size_original >= 0", name="ck_voice_assets_original_size"),
        CheckConstraint("byte_size_encrypted >= 0", name="ck_voice_assets_encrypted_size"),
    )

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    raw_entry_id = Column(String(32), ForeignKey("raw_entries.id"), nullable=True, index=True)
    storage_ref = Column(String(255), nullable=False, unique=True)
    original_filename = Column(String(255), nullable=False)
    media_type = Column(String(128), nullable=True)
    container = Column(String(24), nullable=True)
    byte_size_original = Column(Integer, nullable=False)
    byte_size_encrypted = Column(Integer, nullable=False)
    storage_codec = Column(String(32), nullable=False, default="fernet+zlib-v1")
    content_fingerprint = Column(String(64), nullable=False, index=True)
    transcript_chars = Column(Integer, nullable=False, default=0)
    transcription_language = Column(String(16), nullable=True)
    transcription_mode = Column(String(16), nullable=False, default="local")
    consent_version = Column(String(32), nullable=False)
    retention_purpose = Column(String(64), nullable=False, default="personal_voice_features")
    derived_data_status = Column(String(24), nullable=False, default="not_created")
    created_at_utc = Column(DateTime, default=_utcnow, nullable=False, index=True)

    user = relationship("User", back_populates="voice_assets")


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        Index("ix_ingestion_jobs_user_status", "user_id", "status"),
        Index("ix_ingestion_jobs_user_created", "user_id", "created_at_utc"),
        Index("ix_ingestion_jobs_user_dispatch", "user_id", "status", "queued_at_utc"),
        Index("ix_ingestion_jobs_user_dedup", "user_id", "dedup_key", unique=True),
    )

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    source = Column(String(32), nullable=False, default="api")
    dedup_key = Column(String(160), nullable=True)
    raw_text = Column(Text, nullable=False)
    entry_id = Column(String(32), ForeignKey("raw_entries.id"), nullable=True, index=True)
    error = Column(Text, nullable=True)
    created_at_utc = Column(DateTime, default=_utcnow, index=True)
    queued_at_utc = Column(DateTime, nullable=True)
    started_at_utc = Column(DateTime, nullable=True)
    finished_at_utc = Column(DateTime, nullable=True)
    metadata_json = Column(JSON, default=dict)

    user = relationship("User", back_populates="ingestion_jobs")


class VaultImportSession(Base):
    __tablename__ = "vault_import_sessions"
    __table_args__ = (
        Index("ix_vault_import_sessions_user_status", "user_id", "status"),
        Index("ix_vault_import_sessions_user_created", "user_id", "created_at_utc"),
        Index("ix_vault_import_sessions_expires", "expires_at_utc"),
    )

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="uploading", index=True)
    operation = Column(String(16), nullable=True)
    filename = Column(String(255), nullable=False)
    mode = Column(String(32), nullable=False, default="auto")
    conflict_policy = Column(String(16), nullable=False, default="skip")
    expected_bytes = Column(Integer, nullable=False)
    received_bytes = Column(Integer, nullable=False, default=0)
    archive_sha256 = Column(String(64), nullable=True)
    verified_sha256 = Column(String(64), nullable=True)
    storage_key = Column(String(64), nullable=False, unique=True)
    progress_current = Column(Integer, nullable=False, default=0)
    progress_total = Column(Integer, nullable=False, default=0)
    progress_stage = Column(String(32), nullable=False, default="uploading")
    cancel_requested = Column(Boolean, nullable=False, default=False)
    result_json = Column(JSON, default=dict)
    error = Column(Text, nullable=True)
    created_at_utc = Column(DateTime, default=_utcnow, nullable=False)
    updated_at_utc = Column(DateTime, default=_utcnow, nullable=False)
    started_at_utc = Column(DateTime, nullable=True)
    finished_at_utc = Column(DateTime, nullable=True)
    expires_at_utc = Column(DateTime, nullable=False, index=True)

    user = relationship("User", back_populates="vault_import_sessions")


class ApiIdempotencyRecord(Base):
    __tablename__ = "api_idempotency_records"
    __table_args__ = (
        Index(
            "ix_api_idempotency_user_scope_key",
            "user_id",
            "scope",
            "idempotency_key",
            unique=True,
        ),
        Index("ix_api_idempotency_user_expires", "user_id", "expires_at_utc"),
    )

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    scope = Column(String(255), nullable=False)
    idempotency_key = Column(String(128), nullable=False)
    request_hash = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="in_progress")
    response_status = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    created_at_utc = Column(DateTime, default=_utcnow, nullable=False)
    completed_at_utc = Column(DateTime, nullable=True)
    expires_at_utc = Column(DateTime, nullable=False)

    user = relationship("User", back_populates="idempotency_records")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_user_action", "user_id", "action"),)

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=True, index=True)
    action = Column(String(64), nullable=False, index=True)
    created_at_utc = Column(DateTime, default=_utcnow, index=True)
    metadata_json = Column(JSON, default=dict)


class SafetyReport(Base):
    __tablename__ = "safety_reports"
    __table_args__ = (
        Index("ix_safety_reports_user_status", "user_id", "status"),
        Index("ix_safety_reports_user_created", "user_id", "created_at_utc"),
        Index("ix_safety_reports_category", "category"),
        Index("ix_safety_reports_target_id", "target_id"),
    )

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    category = Column(String(64), nullable=False)
    source = Column(String(32), nullable=False, default="app")
    target_type = Column(String(64), nullable=True)
    target_id = Column(String(64), nullable=True)
    summary = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="received", index=True)
    created_at_utc = Column(DateTime, default=_utcnow, index=True)
    reviewed_at_utc = Column(DateTime, nullable=True)
    metadata_json = Column(JSON, default=dict)

    user = relationship("User", back_populates="safety_reports")


class AppDevice(Base):
    __tablename__ = "app_devices"
    __table_args__ = (
        Index("ix_app_devices_user_installation", "user_id", "installation_id", unique=True),
        Index("ix_app_devices_user_platform", "user_id", "platform"),
    )

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    installation_id = Column(String(128), nullable=False)
    platform = Column(String(16), nullable=False)
    device_name = Column(String(128), nullable=True)
    app_version = Column(String(32), nullable=True)
    build_number = Column(String(32), nullable=True)
    os_version = Column(String(64), nullable=True)
    locale = Column(String(32), nullable=True)
    timezone = Column(String(64), nullable=True)
    push_provider = Column(String(16), nullable=True)
    push_token_hash = Column(String(128), nullable=True, index=True)
    push_token_encrypted = Column(Text, nullable=True)
    notifications_enabled = Column(Boolean, default=False)
    created_at_utc = Column(DateTime, default=_utcnow, index=True)
    last_seen_at_utc = Column(DateTime, default=_utcnow, index=True)
    revoked_at_utc = Column(DateTime, nullable=True, index=True)
    metadata_json = Column(JSON, default=dict)


class ChatConversation(Base):
    __tablename__ = "chat_conversations"
    __table_args__ = (
        Index("ix_chat_conversations_user_key", "user_id", "conversation_key", unique=True),
        Index("ix_chat_conversations_user_updated", "user_id", "updated_at_utc"),
    )

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    conversation_key = Column(String(128), nullable=False)
    surface = Column(String(32), nullable=False, default="api")
    title = Column(String(255), nullable=True)
    created_at_utc = Column(DateTime, default=_utcnow, index=True)
    updated_at_utc = Column(DateTime, default=_utcnow, onupdate=_utcnow, index=True)
    last_message_at_utc = Column(DateTime, nullable=True, index=True)
    metadata_json = Column(JSON, default=dict)

    user = relationship("User", back_populates="chat_conversations")
    messages = relationship("ChatMessage", back_populates="conversation", cascade="all, delete-orphan")
    pending_actions = relationship("PendingChatAction", back_populates="conversation", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chat_messages_user_conversation_created", "user_id", "conversation_id", "created_at_utc"),
        Index("ix_chat_messages_user_role", "user_id", "role"),
        Index(
            "ix_chat_messages_user_conversation_live",
            "user_id",
            "conversation_id",
            "superseded_at_utc",
            "created_at_utc",
        ),
    )

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    conversation_id = Column(String(32), ForeignKey("chat_conversations.id"), nullable=False, index=True)
    role = Column(String(16), nullable=False)
    text = Column(Text, nullable=False)
    route_type = Column(String(64), nullable=True)
    status = Column(String(64), nullable=True)
    raw_entry_id = Column(String(32), ForeignKey("raw_entries.id"), nullable=True, index=True)
    job_id = Column(String(32), ForeignKey("ingestion_jobs.id"), nullable=True, index=True)
    document_id = Column(String(32), ForeignKey("document_sources.id"), nullable=True, index=True)
    created_at_utc = Column(DateTime, default=_utcnow, index=True)
    metadata_json = Column(JSON, default=dict)
    # Set when an earlier turn is edited and resent. The row is kept rather
    # than deleted: this turn may have written a journal entry, and a chat edit
    # is not consent to destroy what was saved.
    superseded_at_utc = Column(DateTime, nullable=True)
    superseded_by_message_id = Column(String(32), nullable=True)

    user = relationship("User", back_populates="chat_messages")
    conversation = relationship("ChatConversation", back_populates="messages")


class PendingChatAction(Base):
    __tablename__ = "pending_chat_actions"
    __table_args__ = (
        Index("ix_pending_chat_actions_user_status_expires", "user_id", "status", "expires_at_utc"),
        Index("ix_pending_chat_actions_user_conversation", "user_id", "conversation_id"),
    )

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    conversation_id = Column(String(32), ForeignKey("chat_conversations.id"), nullable=False, index=True)
    action = Column(String(64), nullable=False)
    args_json = Column(JSON, default=list)
    prompt = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="pending", index=True)
    created_at_utc = Column(DateTime, default=_utcnow, index=True)
    expires_at_utc = Column(DateTime, nullable=False, index=True)
    resolved_at_utc = Column(DateTime, nullable=True)
    metadata_json = Column(JSON, default=dict)

    user = relationship("User", back_populates="pending_chat_actions")
    conversation = relationship("ChatConversation", back_populates="pending_actions")


class RawEntry(Base):
    __tablename__ = "raw_entries"
    __table_args__ = (
        Index("ix_raw_entries_user_date", "user_id", "local_date"),
        Index("ix_raw_entries_user_status", "user_id", "processed_status"),
        Index("ix_raw_entries_user_hash", "user_id", "content_hash"),
        Index("ix_raw_entries_user_importance_date", "user_id", "user_importance", "local_date"),
        CheckConstraint(
            "user_importance IS NULL OR (user_importance >= 1 AND user_importance <= 5)",
            name="ck_raw_entries_user_importance_range",
        ),
    )

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    created_at_utc = Column(DateTime, default=_utcnow, index=True)
    local_date = Column(Date, index=True)
    local_time = Column(String(8))
    source = Column(String(32), default="app")
    telegram_message_id = Column(String(64), nullable=True)
    telegram_chat_id = Column(String(64), nullable=True)
    author_user_id = Column(String(64), nullable=True)
    raw_text = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False, index=True)
    is_private = Column(Boolean, default=False)
    sensitivity = Column(String(64), default="personal")
    processed_status = Column(String(32), default="pending", index=True)
    processing_error = Column(Text, nullable=True)
    user_importance = Column(Integer, nullable=True)
    importance_source = Column(String(32), nullable=True)
    importance_updated_at = Column(DateTime, nullable=True)
    analysis_json = Column(JSON, nullable=True)
    contextual_salience = Column(Float, nullable=True)
    salience_uncertainty = Column(Float, nullable=True)
    salience_model_version = Column(String(32), nullable=True)
    salience_updated_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="raw_entries")
    entity_mentions = relationship("EntityMention", back_populates="raw_entry", cascade="all, delete-orphan")
    memories = relationship("Memory", back_populates="raw_entry", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="raw_entry", cascade="all, delete-orphan")
    action_items = relationship("ActionItem", back_populates="raw_entry", cascade="all, delete-orphan")
    expenses = relationship("Expense", back_populates="raw_entry", cascade="all, delete-orphan")
    relationships_ref = relationship("Relationship", back_populates="raw_entry", cascade="all, delete-orphan")
    document_sources = relationship("DocumentSource", back_populates="raw_entry", cascade="all, delete-orphan")


class Entity(Base):
    __tablename__ = "entities"
    __table_args__ = (Index("ix_entities_user_type_name", "user_id", "type", "canonical_name"),)

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    type = Column(String(32), nullable=False, index=True)
    canonical_name = Column(String(255), nullable=False, index=True)
    aliases_json = Column(JSON, default=list)
    created_at_utc = Column(DateTime, default=_utcnow)
    updated_at_utc = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    sensitivity = Column(String(64), default="personal")
    confidence = Column(String(32), default="observed_by_user")
    notes = Column(Text, nullable=True)
    attributes_json = Column(JSON, default=list)
    salience_score = Column(Float, nullable=True)
    salience_uncertainty = Column(Float, nullable=True)
    salience_signals_json = Column(JSON, nullable=True)
    salience_model_version = Column(String(32), nullable=True)
    salience_updated_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="entities")
    entity_mentions = relationship("EntityMention", back_populates="entity", cascade="all, delete-orphan")
    relationships_source = relationship(
        "Relationship",
        foreign_keys="Relationship.source_entity_id",
        back_populates="source_entity",
        cascade="all, delete-orphan",
    )
    relationships_target = relationship(
        "Relationship",
        foreign_keys="Relationship.target_entity_id",
        back_populates="target_entity",
        cascade="all, delete-orphan",
    )
    events_place = relationship("Event", back_populates="place_entity")
    event_participations = relationship("EventParticipant", back_populates="entity", cascade="all, delete-orphan")


class EntityMention(Base):
    __tablename__ = "entity_mentions"
    __table_args__ = (Index("ix_entity_mentions_user_raw_entry", "user_id", "raw_entry_id"),)

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    raw_entry_id = Column(String(32), ForeignKey("raw_entries.id"), nullable=False, index=True)
    entity_id = Column(String(32), ForeignKey("entities.id"), nullable=False, index=True)
    surface_text = Column(String(255), nullable=False)
    mention_context = Column(Text, nullable=True)
    confidence = Column(String(32), default="observed_by_user")

    raw_entry = relationship("RawEntry", back_populates="entity_mentions")
    entity = relationship("Entity", back_populates="entity_mentions")


class Memory(Base):
    __tablename__ = "memories"
    __table_args__ = (
        Index("ix_memories_user_date", "user_id", "local_date"),
        Index("ix_memories_user_type", "user_id", "memory_type"),
    )

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    raw_entry_id = Column(String(32), ForeignKey("raw_entries.id"), nullable=False, index=True)
    memory_type = Column(String(32), nullable=False, index=True)
    subject_entity_id = Column(String(32), ForeignKey("entities.id"), nullable=True, index=True)
    object_entity_id = Column(String(32), ForeignKey("entities.id"), nullable=True)
    predicate = Column(String(128), nullable=True)
    text = Column(Text, nullable=False)
    structured_json = Column(JSON, nullable=True)
    occurred_at_start = Column(DateTime, nullable=True)
    occurred_at_end = Column(DateTime, nullable=True)
    local_date = Column(Date, index=True)
    sensitivity = Column(String(64), default="personal")
    confidence = Column(String(32), default="observed_by_user")
    source_provenance = Column(Text, nullable=True)
    valid_from = Column(DateTime, nullable=True)
    valid_to = Column(DateTime, nullable=True)
    supersedes_memory_id = Column(String(32), nullable=True)
    created_at_utc = Column(DateTime, default=_utcnow)

    raw_entry = relationship("RawEntry", back_populates="memories")
    subject_entity = relationship("Entity", foreign_keys=[subject_entity_id])
    object_entity = relationship("Entity", foreign_keys=[object_entity_id])


class Relationship(Base):
    __tablename__ = "relationships"
    __table_args__ = (Index("ix_relationships_user_type", "user_id", "relation_type"),)

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    source_entity_id = Column(String(32), ForeignKey("entities.id"), nullable=False, index=True)
    target_entity_id = Column(String(32), ForeignKey("entities.id"), nullable=False, index=True)
    relation_type = Column(String(32), nullable=False, index=True)
    raw_entry_id = Column(String(32), ForeignKey("raw_entries.id"), nullable=False, index=True)
    memory_id = Column(String(32), nullable=True)
    weight = Column(Float, default=1.0)
    confidence = Column(String(32), default="observed_by_user")
    sensitivity = Column(String(64), default="personal")
    first_seen_at = Column(DateTime, default=_utcnow)
    last_seen_at = Column(DateTime, default=_utcnow)
    evidence_count = Column(Integer, default=1)
    notes = Column(Text, nullable=True)

    raw_entry = relationship("RawEntry", back_populates="relationships_ref")
    source_entity = relationship("Entity", foreign_keys=[source_entity_id], back_populates="relationships_source")
    target_entity = relationship("Entity", foreign_keys=[target_entity_id], back_populates="relationships_target")


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_user_date", "user_id", "local_date"),)

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    event_type = Column(String(32), nullable=False, default="other")
    start_at = Column(DateTime, nullable=True)
    end_at = Column(DateTime, nullable=True)
    local_date = Column(Date, index=True)
    place_entity_id = Column(String(32), ForeignKey("entities.id"), nullable=True, index=True)
    summary = Column(Text, nullable=True)
    sensitivity = Column(String(64), default="personal")
    source_raw_entry_id = Column(String(32), ForeignKey("raw_entries.id"), nullable=False)

    raw_entry = relationship("RawEntry", back_populates="events")
    place_entity = relationship("Entity", back_populates="events_place")
    participants = relationship("EventParticipant", back_populates="event", cascade="all, delete-orphan")


class EventParticipant(Base):
    __tablename__ = "event_participants"
    __table_args__ = (Index("ix_event_participants_user_event", "user_id", "event_id"),)

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    event_id = Column(String(32), ForeignKey("events.id"), nullable=False, index=True)
    entity_id = Column(String(32), ForeignKey("entities.id"), nullable=False, index=True)
    role = Column(String(32), default="attendee")

    event = relationship("Event", back_populates="participants")
    entity = relationship("Entity", back_populates="event_participations")


class ActionItem(Base):
    __tablename__ = "action_items"
    __table_args__ = (Index("ix_action_items_user_status", "user_id", "status"),)

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    raw_entry_id = Column(String(32), ForeignKey("raw_entries.id"), nullable=False, index=True)
    description = Column(Text, nullable=False)
    due_at = Column(DateTime, nullable=True)
    owner_entity_id = Column(String(32), ForeignKey("entities.id"), nullable=True)
    status = Column(String(32), default="open")
    sensitivity = Column(String(64), default="personal")

    raw_entry = relationship("RawEntry", back_populates="action_items")


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (Index("ix_expenses_user_raw_entry", "user_id", "raw_entry_id"),)

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    raw_entry_id = Column(String(32), ForeignKey("raw_entries.id"), nullable=False, index=True)
    amount = Column(Float, nullable=True)
    currency = Column(String(8), default="USD")
    merchant_or_place_entity_id = Column(String(32), ForeignKey("entities.id"), nullable=True)
    reason = Column(Text, nullable=True)
    category = Column(String(64), nullable=True)
    confidence = Column(String(32), default="observed_by_user")

    raw_entry = relationship("RawEntry", back_populates="expenses")


class DocumentSource(Base):
    __tablename__ = "document_sources"
    __table_args__ = (
        Index("ix_document_sources_user_created", "user_id", "created_at_utc"),
        Index("ix_document_sources_user_status", "user_id", "status"),
        Index("ix_document_sources_user_hash", "user_id", "content_hash"),
    )

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    raw_entry_id = Column(String(32), ForeignKey("raw_entries.id"), nullable=False, index=True)
    source_type = Column(String(32), nullable=False, default="text")
    title = Column(String(512), nullable=False)
    author = Column(String(255), nullable=True)
    original_url = Column(Text, nullable=True)
    source_url = Column(Text, nullable=True)
    canonical_url = Column(Text, nullable=True)
    source_domain = Column(String(255), nullable=True, index=True)
    access_method = Column(String(32), nullable=True)
    rights_basis = Column(String(32), nullable=True)
    fetch_status = Column(String(32), nullable=True)
    paywall_detected = Column(Boolean, default=False)
    retrieval_quality_score = Column(Float, nullable=True)
    published_at = Column(DateTime, nullable=True)
    content_hash = Column(String(64), nullable=False, index=True)
    raw_text = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="processed", index=True)
    processing_error = Column(Text, nullable=True)
    sensitivity = Column(String(64), default="personal")
    created_at_utc = Column(DateTime, default=_utcnow, index=True)
    local_date = Column(Date, index=True)
    metadata_json = Column(JSON, default=dict)

    raw_entry = relationship("RawEntry", back_populates="document_sources")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (Index("ix_document_chunks_user_document", "user_id", "document_id"),)

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    document_id = Column(String(32), ForeignKey("document_sources.id"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    char_start = Column(Integer, nullable=True)
    char_end = Column(Integer, nullable=True)
    token_count = Column(Integer, nullable=True)
    embedding_id = Column(String(128), nullable=True)
    section_heading = Column(String(255), nullable=True)
    created_at_utc = Column(DateTime, default=_utcnow)
    metadata_json = Column(JSON, default=dict)

    document = relationship("DocumentSource", back_populates="chunks")


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (Index("ix_reports_user_type", "user_id", "report_type"),)

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    created_at_utc = Column(DateTime, default=_utcnow)
    query = Column(Text, nullable=True)
    report_type = Column(String(64), nullable=True)
    output_markdown_path = Column(String(512), nullable=True)
    output_pdf_path = Column(String(512), nullable=True)
    output_html_path = Column(String(512), nullable=True)
    source_memory_ids_json = Column(JSON, default=list)
    source_raw_entry_ids_json = Column(JSON, default=list)


# Imported last, after Base and the journal models exist, so the platform tables
# register on the same metadata. Re-exported here to keep the historical import
# path (`from thoughtpins.db import LlmUsageEvent`) working for callers.
from thoughtpins.db_platform import (  # noqa: E402,F401
    InviteCode,
    InviteRequest,
    LlmUsageEvent,
    MagicLinkToken,
    OperatorNotification,
)

__all__ = [name for name in globals() if not name.startswith("_")]
