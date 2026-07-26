"""OAuth/OIDC ID token verification for Google and Apple."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypedDict

import httpx
import jwt

from thoughtpins.config import config


@dataclass(frozen=True)
class OAuthIdentity:
    provider: str
    subject: str
    email: str | None
    email_verified: bool
    audience: str | None = None
    nonce: str | None = None


_JWKS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_JWKS_TTL_SECONDS = 3600


class _ProviderConfig(TypedDict):
    jwks_url: str
    issuers: set[str]
    audiences: Callable[[], list[str]]
    algorithms: set[str]


_PROVIDERS: dict[str, _ProviderConfig] = {
    "google": {
        "jwks_url": "https://www.googleapis.com/oauth2/v3/certs",
        "issuers": {"accounts.google.com", "https://accounts.google.com"},
        "audiences": lambda: config.GOOGLE_OAUTH_CLIENT_IDS,
        "algorithms": {"RS256"},
    },
    "apple": {
        "jwks_url": "https://appleid.apple.com/auth/keys",
        "issuers": {"https://appleid.apple.com"},
        "audiences": lambda: config.APPLE_OAUTH_CLIENT_IDS,
        "algorithms": {"RS256"},
    },
}


def _fetch_jwks(url: str) -> dict[str, Any]:
    cached = _JWKS_CACHE.get(url)
    now = time.time()
    if cached and now - cached[0] < _JWKS_TTL_SECONDS:
        return cached[1]
    response = httpx.get(url, timeout=5)
    response.raise_for_status()
    data = response.json()
    _JWKS_CACHE[url] = (now, data)
    return data


def verify_oauth_id_token(provider: str, id_token: str) -> OAuthIdentity:
    provider = provider.lower().strip()
    if provider not in _PROVIDERS:
        raise ValueError("Unsupported OAuth provider")

    provider_config = _PROVIDERS[provider]
    audiences = provider_config["audiences"]()
    if not audiences:
        raise ValueError(f"{provider.upper()} OAuth client IDs are not configured")

    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError as exc:
        raise ValueError("OAuth token header is invalid") from exc
    kid = header.get("kid")
    algorithm = header.get("alg")
    if not isinstance(algorithm, str) or algorithm not in provider_config["algorithms"]:
        raise ValueError("OAuth token algorithm is not trusted")
    try:
        jwks = _fetch_jwks(provider_config["jwks_url"])
    except httpx.HTTPError as exc:
        raise ValueError("OAuth signing keys are temporarily unavailable") from exc
    key = next((candidate for candidate in jwks.get("keys", []) if candidate.get("kid") == kid), None)
    if not key:
        raise ValueError("OAuth signing key not found")
    try:
        signing_key = jwt.PyJWK.from_dict(key, algorithm=algorithm).key
    except (jwt.PyJWTError, TypeError, ValueError) as exc:
        raise ValueError("OAuth signing key is invalid") from exc

    last_error: Exception | None = None
    payload: dict[str, Any] | None = None
    matched_audience: str | None = None
    for audience in audiences:
        try:
            payload = jwt.decode(
                id_token,
                signing_key,
                algorithms=[algorithm],
                audience=audience,
                options={"require": ["exp", "iat", "iss", "sub"]},
            )
            matched_audience = audience
            break
        except jwt.PyJWTError as exc:
            last_error = exc
    if payload is None:
        raise ValueError("OAuth token validation failed") from last_error

    if payload.get("iss") not in provider_config["issuers"]:
        raise ValueError("OAuth token issuer is not trusted")

    subject = payload.get("sub")
    if not subject:
        raise ValueError("OAuth token subject is missing")

    email = payload.get("email")
    raw_verified = payload.get("email_verified", False)
    email_verified = raw_verified is True or str(raw_verified).lower() == "true"
    return OAuthIdentity(
        provider=provider,
        subject=subject,
        email=email.strip().lower() if isinstance(email, str) and email.strip() else None,
        email_verified=email_verified,
        audience=matched_audience,
        nonce=payload.get("nonce") if isinstance(payload.get("nonce"), str) else None,
    )
