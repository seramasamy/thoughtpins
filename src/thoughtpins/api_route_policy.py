"""Public and maintenance-safe HTTP route policy."""

from __future__ import annotations

PUBLIC_PATHS = frozenset(
    {
        "/",
        "/app",
        "/app/",
        "/classic",
        "/classic/",
        "/privacy",
        "/terms",
        "/support",
        "/account/delete",
        "/delete-account",
        "/ai-disclosure",
        "/security",
        "/sitemap.xml",
        "/robots.txt",
        "/health",
        "/ready",
        "/v1/health",
        "/v1/health/ready",
        "/v1/client-config",
        "/v1/auth/register",
        "/v1/auth/login",
        "/v1/auth/oauth",
        "/v1/auth/magic-link/request",
        "/v1/auth/magic-link/consume",
        "/v1/auth/magic-code/consume",
        "/v1/auth/email/verify",
        "/v1/auth/refresh",
        "/v1/auth/logout",
        "/register",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/v1/errors",
    }
)

PUBLIC_PREFIXES = ("/app/", "/assets/")

MAINTENANCE_ALWAYS_ALLOWED_PATHS = frozenset(
    {
        "/",
        "/app",
        "/app/",
        "/classic",
        "/classic/",
        "/privacy",
        "/terms",
        "/support",
        "/account/delete",
        "/delete-account",
        "/ai-disclosure",
        "/security",
        "/sitemap.xml",
        "/robots.txt",
        "/health",
        "/ready",
        "/v1/health",
        "/v1/health/ready",
        "/v1/client-config",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/v1/errors",
    }
)

# What an account that has signed in but not yet redeemed an invite may still
# reach. Deliberately an allowlist: a route added later is closed by default
# rather than accidentally exposed, which is the whole point of the gate.
#
# Data rights are never gated. Someone who registered and is waiting can still
# read what the service holds about them, export it, change how they sign in,
# sign out other devices, and delete the account outright. Withholding those
# behind an invitation would be indefensible, and Apple and Google both require
# in-app account deletion regardless of entitlement.
INVITE_EXEMPT_PATHS = frozenset(
    {
        "/v1/me",
        "/v1/invites/status",
        "/v1/invites/redeem",
        "/v1/invites/request",
        "/v1/preferences",
        "/v1/legal/acceptances",
        "/v1/legal/documents",
        "/v1/export",
        "/v1/account/export",
        "/v1/account/sign-in-methods",
        "/v1/account/password",
        "/v1/sessions",
        "/v1/sessions/revoke-others",
        "/v1/errors",
    }
)

# Revoking one session is /v1/sessions/{id}; keep the family reachable so a
# waiting account can still sign itself out anywhere.
INVITE_EXEMPT_PREFIXES = ("/v1/sessions/",)


def is_invite_exempt_path(path: str) -> bool:
    """Whether this path stays open to an account that has not been admitted."""
    normalized = path.rstrip("/") or "/"
    if normalized in INVITE_EXEMPT_PATHS or path in INVITE_EXEMPT_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in INVITE_EXEMPT_PREFIXES)
