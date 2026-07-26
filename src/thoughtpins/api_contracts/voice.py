"""Contracts for explicit personal voice-archive controls."""

from __future__ import annotations

from pydantic import BaseModel, Field


class VoiceArchiveConsentRequest(BaseModel):
    retain_recordings: bool
    acknowledge_sensitive_audio: bool
    acknowledge_personal_use_only: bool
    acknowledge_deletion_available: bool


class VoiceArchiveDeleteRequest(BaseModel):
    confirm: str = Field(..., max_length=32)


class VoiceArchiveStatusResponse(BaseModel):
    enabled: bool
    consent_version: str | None = None
    current_consent_version: str
    consented_at_utc: str | None = None
    asset_count: int = 0
    original_bytes: int = 0
    stored_bytes: int = 0
    default_processing: str = "ephemeral"
    retention_purpose: str = "personal_voice_features"
    derived_voice_data_created: bool = False


class VoiceArchiveDeleteResponse(BaseModel):
    status: str
    deleted: dict[str, int]
