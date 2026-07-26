"""Sign in with Apple server-token exchange and revocation.

This module deliberately handles only Apple's server-side credential lifecycle.
OIDC identity verification remains in :mod:`thoughtpins.oauth`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import httpx
import jwt

from thoughtpins.config import config

APPLE_AUDIENCE = "https://appleid.apple.com"
APPLE_TOKEN_URL = "https://appleid.apple.com/auth/token"
APPLE_REVOKE_URL = "https://appleid.apple.com/auth/revoke"


class AppleOAuthError(RuntimeError):
    """A sanitized Apple credential-lifecycle failure."""


@dataclass(frozen=True)
class AppleTokenGrant:
    refresh_token: str
    id_token: str
    access_token: str | None = None
    expires_in: int | None = None


PostForm = Callable[..., httpx.Response]


def exchange_apple_authorization_code(
    authorization_code: str,
    *,
    client_id: str,
    redirect_uri: str | None = None,
    post_form: PostForm | None = None,
) -> AppleTokenGrant:
    """Exchange a one-time authorization code for Apple's refresh credential."""
    payload = {
        "client_id": client_id,
        "client_secret": create_apple_client_secret(client_id),
        "code": authorization_code,
        "grant_type": "authorization_code",
    }
    if redirect_uri:
        payload["redirect_uri"] = redirect_uri
    response = _post(APPLE_TOKEN_URL, payload, post_form=post_form)
    try:
        body = response.json()
    except ValueError as exc:
        raise AppleOAuthError("Apple returned an invalid credential response") from exc
    refresh_token = body.get("refresh_token") if isinstance(body, dict) else None
    id_token = body.get("id_token") if isinstance(body, dict) else None
    if not isinstance(refresh_token, str) or not refresh_token:
        raise AppleOAuthError("Apple did not return a revocable refresh credential")
    if not isinstance(id_token, str) or not id_token:
        raise AppleOAuthError("Apple did not return an identity token for the authorization code")
    access_token = body.get("access_token")
    expires_in = body.get("expires_in")
    return AppleTokenGrant(
        refresh_token=refresh_token,
        id_token=id_token,
        access_token=access_token if isinstance(access_token, str) else None,
        expires_in=expires_in if isinstance(expires_in, int) else None,
    )


def revoke_apple_refresh_token(
    refresh_token: str,
    *,
    client_id: str,
    post_form: PostForm | None = None,
) -> None:
    """Revoke an Apple refresh credential before removing the local account."""
    _post(
        APPLE_REVOKE_URL,
        {
            "client_id": client_id,
            "client_secret": create_apple_client_secret(client_id),
            "token": refresh_token,
            "token_type_hint": "refresh_token",
        },
        post_form=post_form,
    )


def create_apple_client_secret(client_id: str, *, now: datetime | None = None) -> str:
    """Create a short-lived ES256 client assertion for an allowed Apple client."""
    if client_id not in config.APPLE_OAUTH_CLIENT_IDS:
        raise AppleOAuthError("Apple client is not configured")
    private_key = config.apple_oauth_private_key()
    if not config.APPLE_OAUTH_TEAM_ID or not config.APPLE_OAUTH_KEY_ID or not private_key:
        raise AppleOAuthError("Apple server credentials are not configured")
    issued_at = now or datetime.now(timezone.utc)
    claims = {
        "iss": config.APPLE_OAUTH_TEAM_ID,
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + timedelta(minutes=5)).timestamp()),
        "aud": APPLE_AUDIENCE,
        "sub": client_id,
    }
    try:
        return jwt.encode(
            claims,
            private_key,
            algorithm="ES256",
            headers={"kid": config.APPLE_OAUTH_KEY_ID},
        )
    except (TypeError, ValueError, jwt.PyJWTError) as exc:
        raise AppleOAuthError("Apple server credentials are invalid") from exc


def _post(url: str, payload: dict[str, Any], *, post_form: PostForm | None) -> httpx.Response:
    sender = post_form or httpx.post
    try:
        response = sender(
            url,
            data=payload,
            headers={"Accept": "application/json"},
            timeout=config.APPLE_OAUTH_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response
    except httpx.HTTPError as exc:
        raise AppleOAuthError("Apple credential service is temporarily unavailable") from exc
