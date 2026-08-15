"""Tenant-scoped exhaustive and navigational memory context builders."""

from __future__ import annotations

from thoughtpins.memory.context_sections import (
    build_full_context_lines,
    build_full_context_lines_within,
    build_navigation_context_lines,
)


def build_full_context(session, include_private: bool = False, user_id: str | None = None) -> str:
    """Build exhaustive model context for one tenant and privacy scope."""

    return "\n".join(
        build_full_context_lines(
            session,
            include_private=include_private,
            user_id=user_id,
        )
    )


def build_full_context_within(
    session,
    include_private: bool = False,
    user_id: str | None = None,
    *,
    max_chars: int,
) -> str | None:
    """Return the exhaustive context, or None if it would exceed max_chars.

    Equivalent to calling `build_full_context` and testing its length, except
    that it stops building once the answer is known to be None.
    """

    lines = build_full_context_lines_within(
        session,
        include_private=include_private,
        user_id=user_id,
        max_chars=max_chars,
    )
    return None if lines is None else "\n".join(lines)


def build_navigational_map(session, include_private: bool = False, user_id: str | None = None) -> str:
    """Build a compact index with counts aligned to the selected privacy scope."""

    return "\n".join(
        build_navigation_context_lines(
            session,
            include_private=include_private,
            user_id=user_id,
        )
    )
