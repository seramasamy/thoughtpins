"""Platform tables that support the product without being part of it.

Passwordless sign-in tokens and provider spend metering are operational
concerns: neither holds journal content, and both exist to run the service
rather than to model a user's memory. They live here so ``db.py`` stays the
journal domain and keeps within its line budget.

Imported for its side effect of registering these models on ``Base.metadata``;
``db`` re-exports the names so ``from thoughtpins.db import LlmUsageEvent``
keeps working.
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from thoughtpins.db import Base, _new_id, _utcnow


class MagicLinkToken(Base):
    """A single-use passwordless sign-in token.

    Deliberately keyed by email rather than user_id: the token is issued and
    looked up before any tenant context exists, and may precede the account it
    creates. Same pre-authentication rationale that exempts auth_sessions and
    oauth_credentials from row-level security.
    """

    __tablename__ = "magic_link_tokens"
    __table_args__ = (
        Index("ix_magic_link_tokens_email_created", "email", "created_at_utc"),
        Index("ix_magic_link_tokens_expires", "expires_at_utc"),
    )

    id = Column(String(32), primary_key=True, default=_new_id)
    email = Column(String(255), nullable=False, index=True)
    token_hash = Column(String(128), nullable=False, unique=True, index=True)
    created_at_utc = Column(DateTime, default=_utcnow, nullable=False)
    expires_at_utc = Column(DateTime, nullable=False)
    consumed_at_utc = Column(DateTime, nullable=True)
    request_ip_hash = Column(String(64), nullable=True)
    # Short code for signing in on a device that does not hold the email.
    # Hashed like the link token; attempts are counted so a 6-digit secret
    # cannot be brute forced.
    code_hash = Column(String(128), nullable=True, index=True)
    code_attempts = Column(Integer, nullable=False, default=0)


class LlmUsageEvent(Base):
    """One metered provider call: real token counts and their approximate cost."""

    __tablename__ = "llm_usage_events"
    __table_args__ = (
        Index("ix_llm_usage_events_user_created", "user_id", "created_at_utc"),
        Index("ix_llm_usage_events_created", "created_at_utc"),
    )

    id = Column(String(32), primary_key=True, default=_new_id)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False, index=True)
    created_at_utc = Column(DateTime, default=_utcnow, nullable=False)
    provider = Column(String(32), nullable=False)
    model = Column(String(128), nullable=False)
    operation = Column(String(32), nullable=False)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    # Float matches the existing money-column convention (see Expense.amount).
    cost_usd = Column(Float, nullable=False, default=0.0)
    request_id = Column(String(64), nullable=True)

    user = relationship("User", back_populates="llm_usage_events")


class InviteCode(Base):
    """An admin-issued code that admits an account to the private launch.

    Not tenant data: a code exists before anyone redeems it and may admit
    several people, so there is no owning user to scope it to. Only the hash is
    stored, for the same reason refresh tokens are hashed — a leaked database
    should not hand out working codes.
    """

    __tablename__ = "invite_codes"
    __table_args__ = (Index("ix_invite_codes_expires", "expires_at_utc"),)

    id = Column(String(32), primary_key=True, default=_new_id)
    code_hash = Column(String(128), nullable=False, unique=True, index=True)
    # A human label so codes can be told apart without knowing the code itself.
    label = Column(String(128), nullable=True)
    max_uses = Column(Integer, nullable=False, default=1)
    used_count = Column(Integer, nullable=False, default=0)
    created_at_utc = Column(DateTime, default=_utcnow, nullable=False)
    expires_at_utc = Column(DateTime, nullable=True)
    revoked_at_utc = Column(DateTime, nullable=True)
