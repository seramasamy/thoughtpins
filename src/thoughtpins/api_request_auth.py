"""Blocking request authorization, with the session confined to one worker."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class RequestIdentity:
    user_id: str
    is_admin: bool
    invite_blocked: bool


def resolve_identity(
    request: Request,
    api_key: str | None,
    *,
    session_factory: Callable[[], Session],
    resolve_user: Callable[..., Any],
    invite_blocked: Callable[..., bool],
) -> RequestIdentity | None:
    """Materialize authorization before closing; never return an ORM object."""
    session = session_factory()
    try:
        user = resolve_user(request, session, api_key)
        if user is None:
            return None
        return RequestIdentity(user.id, bool(user.is_admin), invite_blocked(user, request.url.path))
    finally:
        session.close()
