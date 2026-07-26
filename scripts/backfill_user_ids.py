"""Backfill user_id on legacy local rows.

Run after creating the default admin user and before enforcing NOT NULL tenant
columns in a production migration.
"""

from __future__ import annotations

from thoughtpins.db import (
    ActionItem,
    Entity,
    EntityMention,
    Event,
    EventParticipant,
    Expense,
    Memory,
    RawEntry,
    Relationship,
    Report,
)
from thoughtpins.store import get_session, init_db
from thoughtpins.users import get_or_create_default_user

MODELS = [
    RawEntry,
    Entity,
    EntityMention,
    Memory,
    Relationship,
    Event,
    EventParticipant,
    ActionItem,
    Expense,
    Report,
]


def main() -> None:
    init_db()
    session = get_session()
    try:
        user = get_or_create_default_user(session=session)
        total = 0
        for model in MODELS:
            rows = session.query(model).filter(model.user_id.is_(None)).all()
            for row in rows:
                row.user_id = user.id
            total += len(rows)
            print(f"{model.__tablename__}: {len(rows)}")
        session.commit()
        print(f"Backfilled {total} rows to user {user.id}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
