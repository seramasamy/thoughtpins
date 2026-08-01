"""Account lifecycle, preferences, safety reporting, and device routes."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from thoughtpins.api_contracts import (
    AccountDeleteRequest,
    DeviceRegistrationRequest,
    DeviceResponse,
    DevicesPageResponse,
    LegalAcceptanceRequest,
    PasswordSetRequest,
    PasswordSetResponse,
    SafetyReportRequest,
    SafetyReportResponse,
    SessionResponse,
    SessionsPageResponse,
    SignInMethodsResponse,
)
from thoughtpins.api_preferences import (
    PreferencesResponse,
    PreferencesUpdateRequest,
    preferences_response,
    upsert_app_preferences,
)
from thoughtpins.apple_oauth import revoke_apple_refresh_token
from thoughtpins.audit import record_audit_event
from thoughtpins.auth import hash_refresh_token
from thoughtpins.config import config
from thoughtpins.credentials import (
    CredentialProofRequired,
    CredentialProofUnavailable,
    set_password,
    sign_in_methods,
)
from thoughtpins.crypto import encrypt_for_storage
from thoughtpins.data_lifecycle import DataDeletionUnavailable, delete_user_data, export_user_data
from thoughtpins.db import AppDevice, AuthSession, ChatMessage, DocumentSource, RawEntry, SafetyReport, User
from thoughtpins.oauth_accounts import revoke_apple_credentials
from thoughtpins.store import get_session


def create_account_router(
    *,
    current_user_dependency: Callable[..., str],
    current_session_dependency: Callable[..., str | None],
    revoke_apple_token_fn: Callable[..., None] | None = None,
) -> APIRouter:
    router = APIRouter()
    apple_token_revoker = revoke_apple_token_fn or revoke_apple_refresh_token

    @router.get("/v1/export")
    @router.get("/v1/account/export")
    async def export_account(user_id: str = Depends(current_user_dependency)) -> dict[str, Any]:
        session = get_session()
        try:
            payload = export_user_data(session, user_id)
            record_audit_event(session, user_id=user_id, action="account.export")
            return payload
        finally:
            session.close()

    @router.get("/v1/me")
    async def me(user_id: str = Depends(current_user_dependency)) -> dict[str, Any]:
        session = get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            return {
                "id": user.id,
                "email": user.email,
                "phone": user.phone,
                "display_name": user.display_name,
                "is_admin": user.is_admin,
                "auth_method": user.auth_method,
                "created_at_utc": user.created_at_utc.isoformat() if user.created_at_utc else None,
                "last_login_utc": user.last_login_utc.isoformat() if user.last_login_utc else None,
            }
        finally:
            session.close()

    @router.get("/v1/account/sign-in-methods", response_model=SignInMethodsResponse)
    async def get_sign_in_methods(user_id: str = Depends(current_user_dependency)) -> SignInMethodsResponse:
        session = get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            return SignInMethodsResponse(**sign_in_methods(session, user))
        finally:
            session.close()

    @router.post("/v1/account/password", response_model=PasswordSetResponse)
    async def set_account_password(
        request_model: PasswordSetRequest,
        user_id: str = Depends(current_user_dependency),
        current_session_id: str | None = Depends(current_session_dependency),
    ) -> PasswordSetResponse:
        session = get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            had_password = bool(user.password_hash)
            try:
                revoked = set_password(
                    session,
                    user,
                    new_password=request_model.new_password,
                    current_password=request_model.current_password,
                    code=request_model.code,
                    current_auth_session_id=current_session_id,
                )
            except CredentialProofUnavailable as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except CredentialProofRequired as exc:
                record_audit_event(
                    session,
                    user_id=user_id,
                    action="auth.password_set_rejected",
                    metadata={"had_password": had_password},
                )
                raise HTTPException(status_code=403, detail=str(exc)) from exc
            record_audit_event(
                session,
                user_id=user_id,
                action="auth.password_changed" if had_password else "auth.password_added",
                metadata={"other_sessions_revoked": revoked},
            )
            return PasswordSetResponse(status="ok", password_set=True, other_sessions_revoked=revoked)
        finally:
            session.close()

    @router.get("/v1/preferences", response_model=PreferencesResponse)
    async def get_preferences(user_id: str = Depends(current_user_dependency)) -> PreferencesResponse:
        session = get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            return preferences_response(user)
        finally:
            session.close()

    @router.patch("/v1/preferences", response_model=PreferencesResponse)
    async def update_preferences(
        request_model: PreferencesUpdateRequest,
        user_id: str = Depends(current_user_dependency),
    ) -> PreferencesResponse:
        session = get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            payload = request_model.model_dump(exclude_unset=True)
            if (
                "private_entries_in_ask" in payload
                and payload["private_entries_in_ask"]
                and not config.PRIVATE_ALLOW_LLM
            ):
                raise HTTPException(status_code=403, detail="Private-entry LLM context is disabled by server policy")
            upsert_app_preferences(user, payload)
            record_audit_event(
                session,
                user_id=user_id,
                action="preferences.updated",
                metadata={"fields": sorted(payload)},
            )
            session.commit()
            return preferences_response(user)
        finally:
            session.close()

    @router.post("/v1/legal/acceptances", response_model=PreferencesResponse)
    async def accept_legal_document(
        request_model: LegalAcceptanceRequest,
        user_id: str = Depends(current_user_dependency),
    ) -> PreferencesResponse:
        session = get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            preferences = dict(user.preferences_json or {})
            acceptances = dict(preferences.get("legal_acceptances") or {})
            acceptances[request_model.document] = {
                "version": request_model.version,
                "accepted_at_utc": _utcnow().isoformat(),
            }
            preferences["legal_acceptances"] = acceptances
            user.preferences_json = preferences
            record_audit_event(
                session,
                user_id=user_id,
                action="legal.accepted",
                metadata={"document": request_model.document, "version": request_model.version},
            )
            session.commit()
            return preferences_response(user)
        finally:
            session.close()

    @router.post("/v1/safety/reports", response_model=SafetyReportResponse, status_code=201)
    async def create_safety_report(
        request_model: SafetyReportRequest,
        request: Request,
        user_id: str = Depends(current_user_dependency),
    ) -> SafetyReportResponse:
        session = get_session()
        try:
            _validate_safety_report_target(
                session,
                user_id=user_id,
                target_type=request_model.target_type,
                target_id=request_model.target_id,
            )
            report = SafetyReport(
                user_id=user_id,
                category=request_model.category,
                source=request_model.source,
                target_type=request_model.target_type,
                target_id=request_model.target_id,
                summary=request_model.summary,
                status="received",
                metadata_json=_safety_report_metadata(request_model, request),
            )
            session.add(report)
            session.commit()
            session.refresh(report)
            record_audit_event(
                session,
                user_id=user_id,
                action="safety.report.created",
                metadata={
                    "report_id": report.id,
                    "category": report.category,
                    "target_type": report.target_type,
                    "source": report.source,
                },
            )
            return SafetyReportResponse(
                id=report.id,
                status=report.status,
                category=report.category,
                created_at_utc=report.created_at_utc.isoformat() if report.created_at_utc else None,
            )
        finally:
            session.close()

    @router.get("/v1/devices", response_model=DevicesPageResponse)
    async def list_devices(user_id: str = Depends(current_user_dependency)) -> DevicesPageResponse:
        session = get_session()
        try:
            devices = (
                session.query(AppDevice)
                .filter(AppDevice.user_id == user_id)
                .order_by(AppDevice.revoked_at_utc.is_not(None), AppDevice.last_seen_at_utc.desc())
                .all()
            )
            return DevicesPageResponse(items=[_device_response(device) for device in devices], total=len(devices))
        finally:
            session.close()

    @router.post("/v1/devices", response_model=DeviceResponse)
    async def register_device(
        request_model: DeviceRegistrationRequest,
        user_id: str = Depends(current_user_dependency),
    ) -> DeviceResponse:
        session = get_session()
        try:
            device = (
                session.query(AppDevice)
                .filter(
                    AppDevice.user_id == user_id,
                    AppDevice.installation_id == request_model.installation_id,
                )
                .first()
            )
            if not device:
                device = AppDevice(
                    user_id=user_id,
                    installation_id=request_model.installation_id,
                    platform=request_model.platform,
                )
                session.add(device)

            encrypted_token = encrypt_for_storage(request_model.push_token) if request_model.push_token else None
            if request_model.push_token and config.is_production() and encrypted_token is None:
                raise HTTPException(status_code=500, detail="Push token encryption unavailable")

            device.platform = request_model.platform
            device.device_name = request_model.device_name
            device.app_version = request_model.app_version
            device.build_number = request_model.build_number
            device.os_version = request_model.os_version
            device.locale = request_model.locale
            device.timezone = request_model.timezone
            device.push_provider = request_model.push_provider
            if request_model.push_token:
                device.push_token_hash = hash_refresh_token(request_model.push_token)
                device.push_token_encrypted = encrypted_token
            device.notifications_enabled = request_model.notifications_enabled
            device.last_seen_at_utc = _utcnow()
            device.revoked_at_utc = None
            device.metadata_json = request_model.metadata
            record_audit_event(
                session,
                user_id=user_id,
                action="device.registered",
                metadata={
                    "platform": request_model.platform,
                    "installation_id": request_model.installation_id,
                },
            )
            session.commit()
            return _device_response(device)
        finally:
            session.close()

    @router.get("/v1/sessions", response_model=SessionsPageResponse)
    async def list_auth_sessions(
        user_id: str = Depends(current_user_dependency),
        current_session_id: str | None = Depends(current_session_dependency),
    ) -> SessionsPageResponse:
        session = get_session()
        try:
            rows = (
                session.query(AuthSession)
                .filter(
                    AuthSession.user_id == user_id,
                    AuthSession.revoked_at_utc.is_(None),
                    AuthSession.expires_at_utc > _utcnow(),
                )
                .order_by(AuthSession.created_at_utc.desc(), AuthSession.id.desc())
                .all()
            )
            return SessionsPageResponse(
                items=[_session_response(row, current_session_id=current_session_id) for row in rows],
                total=len(rows),
            )
        finally:
            session.close()

    @router.delete("/v1/sessions/{session_id}", response_model=SessionResponse)
    async def revoke_auth_session(
        session_id: str,
        user_id: str = Depends(current_user_dependency),
        current_session_id: str | None = Depends(current_session_dependency),
    ) -> SessionResponse:
        session = get_session()
        try:
            auth_session = (
                session.query(AuthSession).filter(AuthSession.id == session_id, AuthSession.user_id == user_id).first()
            )
            if not auth_session:
                raise HTTPException(status_code=404, detail="Session not found")
            if auth_session.revoked_at_utc is None:
                auth_session.revoked_at_utc = _utcnow()
                session.commit()
                record_audit_event(
                    session,
                    user_id=user_id,
                    action="auth.session_revoked",
                    metadata={"session_id": auth_session.id, "current": auth_session.id == current_session_id},
                )
            return _session_response(auth_session, current_session_id=current_session_id)
        finally:
            session.close()

    @router.post("/v1/sessions/revoke-others")
    async def revoke_other_auth_sessions(
        user_id: str = Depends(current_user_dependency),
        current_session_id: str | None = Depends(current_session_dependency),
    ) -> dict[str, int | str]:
        session = get_session()
        try:
            query = session.query(AuthSession).filter(
                AuthSession.user_id == user_id,
                AuthSession.revoked_at_utc.is_(None),
                AuthSession.expires_at_utc > _utcnow(),
            )
            if current_session_id:
                query = query.filter(AuthSession.id != current_session_id)
            rows = query.all()
            now = _utcnow()
            for auth_session in rows:
                auth_session.revoked_at_utc = now
            session.commit()
            record_audit_event(
                session,
                user_id=user_id,
                action="auth.other_sessions_revoked",
                metadata={"count": len(rows)},
            )
            return {"status": "revoked", "count": len(rows)}
        finally:
            session.close()

    @router.delete("/v1/devices/{installation_id}", response_model=DeviceResponse)
    async def revoke_device(
        installation_id: str,
        user_id: str = Depends(current_user_dependency),
    ) -> DeviceResponse:
        session = get_session()
        try:
            device = (
                session.query(AppDevice)
                .filter(
                    AppDevice.user_id == user_id,
                    AppDevice.installation_id == installation_id,
                )
                .first()
            )
            if not device:
                raise HTTPException(status_code=404, detail="Device not found")
            device.revoked_at_utc = _utcnow()
            device.notifications_enabled = False
            device.push_token_hash = None
            device.push_token_encrypted = None
            record_audit_event(
                session,
                user_id=user_id,
                action="device.revoked",
                metadata={"platform": device.platform, "installation_id": installation_id},
            )
            session.commit()
            return _device_response(device)
        finally:
            session.close()

    @router.delete("/v1/me")
    @router.delete("/v1/account")
    async def delete_account(
        request_model: AccountDeleteRequest,
        user_id: str = Depends(current_user_dependency),
    ) -> dict[str, Any]:
        if request_model.confirm != "DELETE":
            raise HTTPException(status_code=400, detail="confirm must equal DELETE")
        session = get_session()
        try:
            revocation = revoke_apple_credentials(
                session,
                user_id,
                revoke_fn=apple_token_revoker,
            )
            if revocation["failed"]:
                session.rollback()
                raise HTTPException(
                    status_code=503,
                    detail="Sign in with Apple revocation is temporarily unavailable; the account was not deleted.",
                )
            record_audit_event(
                session,
                user_id=user_id,
                action="account.delete_requested",
                metadata={"apple_revocation": revocation},
            )
            try:
                deleted = delete_user_data(session, user_id)
            except DataDeletionUnavailable as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            return {"status": "deleted", "deleted": deleted, "provider_revocation": revocation}
        finally:
            session.close()

    return router


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _device_response(device: AppDevice) -> DeviceResponse:
    return DeviceResponse(
        id=device.id,
        installation_id=device.installation_id,
        platform=device.platform,
        device_name=device.device_name,
        app_version=device.app_version,
        build_number=device.build_number,
        os_version=device.os_version,
        locale=device.locale,
        timezone=device.timezone,
        push_provider=device.push_provider,
        push_token_present=bool(device.push_token_hash),
        notifications_enabled=bool(device.notifications_enabled),
        created_at_utc=device.created_at_utc.isoformat() if device.created_at_utc else None,
        last_seen_at_utc=device.last_seen_at_utc.isoformat() if device.last_seen_at_utc else None,
        revoked_at_utc=device.revoked_at_utc.isoformat() if device.revoked_at_utc else None,
    )


def _session_response(auth_session: AuthSession, *, current_session_id: str | None) -> SessionResponse:
    return SessionResponse(
        id=auth_session.id,
        current=auth_session.id == current_session_id,
        created_at_utc=auth_session.created_at_utc.isoformat() if auth_session.created_at_utc else None,
        expires_at_utc=auth_session.expires_at_utc.isoformat() if auth_session.expires_at_utc else None,
        revoked_at_utc=auth_session.revoked_at_utc.isoformat() if auth_session.revoked_at_utc else None,
        user_agent=auth_session.user_agent,
        ip_address=auth_session.ip_address,
    )


def _safety_report_metadata(request_model: SafetyReportRequest, request: Request) -> dict[str, Any]:
    raw = dict(request_model.metadata or {})
    blocked_keys = {
        "text",
        "body",
        "content",
        "message",
        "summary",
        "raw_text",
        "password",
        "token",
        "authorization",
    }
    safe_client_metadata = {
        str(key)[:64]: _json_safe(value)
        for key, value in list(raw.items())[:12]
        if str(key).strip().lower() not in blocked_keys
    }
    return {
        "client_request_id": getattr(request.state, "request_id", ""),
        "user_agent_present": bool(request.headers.get("User-Agent")),
        "client_metadata": safe_client_metadata,
    }


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        return json.loads(json.dumps(value, default=str))


def _validate_safety_report_target(
    session,
    *,
    user_id: str,
    target_type: str | None,
    target_id: str | None,
) -> None:
    if not target_id or not target_type or target_type in {"general", "account", "memory_card"}:
        return
    model = {
        "chat_message": ChatMessage,
        "document_source": DocumentSource,
        "raw_entry": RawEntry,
    }.get(target_type)
    if model is None:
        return
    exists = session.query(model.id).filter(model.user_id == user_id, model.id == target_id).first()
    if not exists:
        raise HTTPException(status_code=404, detail="Safety report target not found")
