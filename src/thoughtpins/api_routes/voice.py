"""Privacy-first routes for optional retained voice notes."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException

from thoughtpins.api_contracts.voice import (
    VoiceArchiveConsentRequest,
    VoiceArchiveDeleteRequest,
    VoiceArchiveDeleteResponse,
    VoiceArchiveStatusResponse,
)
from thoughtpins.audit import record_audit_event
from thoughtpins.config import config
from thoughtpins.db import User
from thoughtpins.store import get_session
from thoughtpins.voice_archive import (
    VOICE_ARCHIVE_DELETE_CONFIRMATION,
    VoiceArchiveError,
    delete_voice_archive,
    disable_voice_archive,
    enable_voice_archive,
    voice_archive_status,
)


def create_voice_router(*, current_user_dependency: Callable[..., str]) -> APIRouter:
    router = APIRouter()

    def require_voice_archive() -> None:
        if not config.VOICE_ARCHIVE_ENABLED:
            raise HTTPException(status_code=404, detail="Personal voice archive is unavailable")

    @router.get("/v1/voice-archive", response_model=VoiceArchiveStatusResponse)
    async def get_voice_archive(user_id: str = Depends(current_user_dependency)) -> VoiceArchiveStatusResponse:
        require_voice_archive()
        session = get_session()
        try:
            return VoiceArchiveStatusResponse(**voice_archive_status(session, user_id))
        finally:
            session.close()

    @router.post("/v1/voice-archive/consent", response_model=VoiceArchiveStatusResponse)
    async def consent_to_voice_archive(
        payload: VoiceArchiveConsentRequest,
        user_id: str = Depends(current_user_dependency),
    ) -> VoiceArchiveStatusResponse:
        require_voice_archive()
        if not all(
            (
                payload.retain_recordings,
                payload.acknowledge_sensitive_audio,
                payload.acknowledge_personal_use_only,
                payload.acknowledge_deletion_available,
            )
        ):
            raise HTTPException(status_code=400, detail="All voice archive confirmations are required")
        session = get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            try:
                enable_voice_archive(user)
            except VoiceArchiveError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            session.commit()
            record_audit_event(
                session,
                user_id=user_id,
                action="voice.archive.consent_enabled",
                metadata={"purpose": "personal_voice_features"},
            )
            return VoiceArchiveStatusResponse(**voice_archive_status(session, user_id))
        finally:
            session.close()

    @router.delete("/v1/voice-archive/consent", response_model=VoiceArchiveStatusResponse)
    async def withdraw_voice_archive_consent(
        user_id: str = Depends(current_user_dependency),
    ) -> VoiceArchiveStatusResponse:
        require_voice_archive()
        session = get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            disable_voice_archive(user)
            session.commit()
            record_audit_event(session, user_id=user_id, action="voice.archive.consent_disabled")
            return VoiceArchiveStatusResponse(**voice_archive_status(session, user_id))
        finally:
            session.close()

    @router.delete("/v1/voice-archive", response_model=VoiceArchiveDeleteResponse)
    async def delete_retained_voice(
        payload: VoiceArchiveDeleteRequest,
        user_id: str = Depends(current_user_dependency),
    ) -> VoiceArchiveDeleteResponse:
        require_voice_archive()
        if payload.confirm != VOICE_ARCHIVE_DELETE_CONFIRMATION:
            raise HTTPException(status_code=400, detail=f"confirm must equal {VOICE_ARCHIVE_DELETE_CONFIRMATION}")
        session = get_session()
        try:
            try:
                deleted = delete_voice_archive(session, user_id)
            except VoiceArchiveError as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc
            record_audit_event(
                session,
                user_id=user_id,
                action="voice.archive.deleted",
                metadata={"asset_count": deleted["voice_assets"], "stored_bytes": deleted["stored_bytes"]},
            )
            return VoiceArchiveDeleteResponse(status="deleted", deleted=deleted)
        finally:
            session.close()

    return router
