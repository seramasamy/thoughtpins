"""Tenant context helpers for request-scoped database isolation."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

_current_tenant_id: ContextVar[str | None] = ContextVar("thoughtpins_current_tenant_id", default=None)


def get_current_tenant_id() -> str | None:
    return _current_tenant_id.get()


@contextmanager
def tenant_context(user_id: str | None) -> Iterator[None]:
    token = _current_tenant_id.set(user_id)
    try:
        yield
    finally:
        _current_tenant_id.reset(token)
