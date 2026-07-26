"""Shared tenant scoping for memory-context queries."""

from __future__ import annotations


def scope_user(query, model, user_id: str | None):
    """Restrict a SQLAlchemy query when a tenant identifier is available."""

    if user_id:
        return query.filter(model.user_id == user_id)
    return query
