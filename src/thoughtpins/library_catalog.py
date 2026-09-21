"""Tenant-scoped, paginated source browsing without touching the ranking path."""

from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from thoughtpins.db import DocumentSource


def list_documents(
    session: Session, user_id: str, *, limit: int = 20, offset: int = 0, query: str = ""
) -> list[DocumentSource]:
    sources = session.query(DocumentSource).filter(DocumentSource.user_id == user_id)
    if query.strip():
        literal = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{literal}%"
        sources = sources.filter(
            or_(
                DocumentSource.title.ilike(pattern, escape="\\"),
                DocumentSource.author.ilike(pattern, escape="\\"),
                DocumentSource.source_domain.ilike(pattern, escape="\\"),
            )
        )
    return (
        sources.order_by(DocumentSource.created_at_utc.desc(), DocumentSource.id.desc())
        .offset(max(0, offset))
        .limit(max(1, min(100, limit)))
        .all()
    )
