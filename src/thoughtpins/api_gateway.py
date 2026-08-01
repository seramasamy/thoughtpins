"""Everything decided about a request before a route sees it.

Who is calling, whether the path is public, whether the private launch closes
it, whether the body is too big, and which rate limit applies. Split out of
api.py, which had grown past its size ratchet: these are one concern and none of
them are routes.
"""

from __future__ import annotations

import re
import secrets
import uuid

from fastapi import Request

from thoughtpins.api_route_policy import (
    MAINTENANCE_ALWAYS_ALLOWED_PATHS,
    PUBLIC_PATHS,
    PUBLIC_PREFIXES,
    is_invite_exempt_path,
)
from thoughtpins.auth import authenticate_access_token, decode_access_token
from thoughtpins.config import config
from thoughtpins.invites import admitted as invite_admitted
from thoughtpins.users import get_or_create_default_user, get_user_by_api_key
from thoughtpins.vault.import_archive import MAX_ARCHIVE_BYTES


def _extract_api_key(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return request.headers.get("X-API-Key", "").strip()


def _is_public_path(path: str) -> bool:
    return path in PUBLIC_PATHS or any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)


def _resolve_request_user(request: Request, session, key: str | None):
    """Identify the caller from a bearer token, an API key, or open local mode.

    Order matters: a bearer token is the real user-facing path, the shared API
    key is operational, and the last branch only applies where authentication is
    switched off entirely. Lifted out of the middleware, which had grown past
    its complexity budget with the private-launch check added.
    """
    user = None
    bearer = request.headers.get("Authorization", "").lower().startswith("bearer ")
    if bearer and key:
        user = authenticate_access_token(session, key)
        payload = decode_access_token(key) if user else None
        request.state.auth_session_id = str((payload or {}).get("sid") or "") or None
    if user:
        return user
    if config.API_KEY and key and secrets.compare_digest(key, config.API_KEY):
        return get_or_create_default_user(session=session)
    if config.ALLOW_USER_API_KEYS and key:
        return get_user_by_api_key(key, session=session)
    if not config.REQUIRE_API_AUTH:
        return get_or_create_default_user(session=session)
    return None


def _is_invite_blocked(user, path: str) -> bool:
    """Whether the private launch closes this path to this account.

    Kept out of the middleware so the request path there stays readable; the
    decision itself is two questions, and both belong together.
    """
    return not invite_admitted(user) and not is_invite_exempt_path(path)


def _is_maintenance_allowed(request: Request) -> bool:
    if request.method in {"OPTIONS", "HEAD"}:
        return True
    path = request.url.path
    if path in MAINTENANCE_ALWAYS_ALLOWED_PATHS or any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES):
        return True
    if config.MAINTENANCE_ALLOW_READS and request.method == "GET":
        return True
    return False


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else None


def _safe_request_id(raw: str | None) -> str:
    if raw:
        candidate = raw.strip()
        if 1 <= len(candidate) <= 128 and re.fullmatch(r"[A-Za-z0-9_.:-]+", candidate):
            return candidate
    return uuid.uuid4().hex


def _content_length_too_large(request: Request) -> bool:
    raw = request.headers.get("Content-Length")
    if not raw:
        return False
    try:
        limit = config.MAX_REQUEST_BODY_BYTES
        if request.url.path in {"/v1/uploads", "/v1/import/obsidian"}:
            largest_binary = max(MAX_ARCHIVE_BYTES, 25 * 1024 * 1024)
            base64_json_limit = 4 * ((largest_binary + 2) // 3) + 64 * 1024
            limit = max(limit, base64_json_limit)
        return int(raw) > limit
    except ValueError:
        return False


def _security_headers() -> dict[str, str]:
    if not config.SECURITY_HEADERS_ENABLED:
        return {}
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "camera=(), microphone=(self), geolocation=()",
    }
    if config.is_production():
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return headers


def _rate_limit_for_path(path: str) -> int:
    if path.startswith("/v1/auth/"):
        return config.RATE_LIMIT_AUTH_PER_MINUTE
    if path in {"/v1/entries", "/v1/entries/async", "/v1/uploads", "/v1/import/obsidian", "/ingest"}:
        return config.RATE_LIMIT_INGEST_PER_MINUTE
    if path in {"/v1/ask", "/ask", "/v1/chat"}:
        return config.RATE_LIMIT_LLM_PER_MINUTE
    if path.startswith("/v1/export") or path.startswith("/export") or path.startswith("/v1/account/export"):
        return config.RATE_LIMIT_EXPORT_PER_MINUTE
    if path.startswith("/v1/safety/"):
        return config.RATE_LIMIT_ACCOUNT_PER_MINUTE
    if path in {"/v1/me", "/v1/account"}:
        return config.RATE_LIMIT_ACCOUNT_PER_MINUTE
    return config.RATE_LIMIT_PER_MINUTE
