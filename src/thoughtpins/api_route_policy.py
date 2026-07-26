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
