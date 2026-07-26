"""User management for API keys and optional Telegram bindings."""

from __future__ import annotations

import secrets
from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from thoughtpins.config import config
from thoughtpins.db import User
from thoughtpins.privacy import fingerprint_identifier
from thoughtpins.store import get_session


def _generate_api_key() -> str:
    return "tp_" + secrets.token_urlsafe(32)


def get_or_create_default_user(session: Session | None = None) -> User:
    """Get the local default admin user used for development and legacy flows."""
    if session is None:
        session = get_session()
        close_session = True
    else:
        close_session = False

    try:
        user = (
            session.query(User)
            .filter(
                User.is_admin == True,
                User.is_active == True,
                User.deleted_at_utc.is_(None),
            )
            .first()
        )
        if not user:
            user = User(
                email=config.DEFAULT_ADMIN_EMAIL or None,
                display_name=config.DEFAULT_DISPLAY_NAME,
                api_key=_generate_api_key(),
                is_admin=True,
                auth_method="api_key",
                telegram_chat_id=config.DEFAULT_TELEGRAM_CHAT_ID or None,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            logger.info("Created default admin user {}", user.id)
        return user
    finally:
        if close_session:
            session.close()


def get_or_create_user_for_telegram(chat_id: str, session: Session | None = None) -> User:
    """Resolve a Telegram chat to a user, creating a local user when allowed."""
    if session is None:
        session = get_session()
        close_session = True
    else:
        close_session = False

    try:
        user = get_user_by_telegram(chat_id, session=session)
        if user:
            return user

        if config.SYSTEM_LOCKED:
            allowed_chat_ids = {str(chat_id) for chat_id in config.TELEGRAM_ALLOWED_USER_IDS}
            is_configured_chat = bool(config.DEFAULT_TELEGRAM_CHAT_ID) and str(config.DEFAULT_TELEGRAM_CHAT_ID) == str(
                chat_id
            )
            is_allowed_chat = str(chat_id) in allowed_chat_ids
            is_local_test_chat = config.TELEGRAM_TEST_MODE and not config.is_production()
            if is_configured_chat or is_allowed_chat or is_local_test_chat:
                user = User(
                    display_name=f"Telegram {chat_id}",
                    api_key=_generate_api_key(),
                    telegram_chat_id=str(chat_id),
                    auth_method="telegram",
                )
                session.add(user)
                session.commit()
                session.refresh(user)
                logger.info(
                    "Created Telegram-bound user {} for locked telegram_hash={}",
                    user.id,
                    fingerprint_identifier(chat_id),
                )
                return user
            return get_or_create_default_user(session=session)

        user = User(
            display_name=f"Telegram {chat_id}",
            api_key=_generate_api_key(),
            telegram_chat_id=str(chat_id),
            auth_method="telegram",
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        logger.info("Created Telegram-bound user {} for telegram_hash={}", user.id, fingerprint_identifier(chat_id))
        return user
    finally:
        if close_session:
            session.close()


def get_user_by_id(user_id: str, session: Session | None = None) -> Optional[User]:
    """Find an active user by internal ID."""
    if session is None:
        session = get_session()
        close_session = True
    else:
        close_session = False
    try:
        return (
            session.query(User)
            .filter(
                User.id == user_id,
                User.is_active == True,
                User.deleted_at_utc.is_(None),
            )
            .first()
        )
    finally:
        if close_session:
            session.close()


def lock_active_user_for_write(session: Session, user_id: str) -> User:
    """Coordinate tenant writes with account deletion on PostgreSQL.

    PostgreSQL emits ``FOR SHARE`` here; SQLite safely ignores the hint in
    founder development. The lock lasts until the caller commits or rolls back.
    """
    with session.no_autoflush:
        user = (
            session.query(User)
            .filter(
                User.id == user_id,
                User.is_active == True,
                User.deleted_at_utc.is_(None),
            )
            .with_for_update(read=True)
            .first()
        )
    if not user:
        raise ValueError("User account is inactive")
    return user


def get_user_by_telegram(chat_id: str, session: Session | None = None) -> Optional[User]:
    """Find an active user by Telegram chat ID."""
    if session is None:
        session = get_session()
        close_session = True
    else:
        close_session = False
    try:
        return (
            session.query(User)
            .filter(
                User.telegram_chat_id == str(chat_id),
                User.is_active == True,
                User.deleted_at_utc.is_(None),
            )
            .first()
        )
    finally:
        if close_session:
            session.close()


def get_user_by_api_key(api_key: str, session: Session | None = None) -> Optional[User]:
    """Find an active user by API key."""
    if session is None:
        session = get_session()
        close_session = True
    else:
        close_session = False
    try:
        return (
            session.query(User)
            .filter(
                User.api_key == api_key,
                User.is_active == True,
                User.deleted_at_utc.is_(None),
            )
            .first()
        )
    finally:
        if close_session:
            session.close()


def get_user_by_email(email: str, session: Session | None = None) -> Optional[User]:
    """Find an active user by normalized email."""
    if session is None:
        session = get_session()
        close_session = True
    else:
        close_session = False
    try:
        normalized = email.strip().lower()
        return (
            session.query(User)
            .filter(
                User.email == normalized,
                User.is_active == True,
                User.deleted_at_utc.is_(None),
            )
            .first()
        )
    finally:
        if close_session:
            session.close()


def get_user_by_phone(phone: str, session: Session | None = None) -> Optional[User]:
    """Find an active user by normalized phone number."""
    if session is None:
        session = get_session()
        close_session = True
    else:
        close_session = False
    try:
        normalized = phone.strip()
        return (
            session.query(User)
            .filter(
                User.phone == normalized,
                User.is_active == True,
                User.deleted_at_utc.is_(None),
            )
            .first()
        )
    finally:
        if close_session:
            session.close()


def register_user(
    email: str | None = None,
    phone: str | None = None,
    display_name: str | None = None,
    telegram_chat_id: str | None = None,
    password_hash: str | None = None,
    session: Session | None = None,
    bypass_system_lock: bool = False,
) -> User:
    """Register a user through the current API-key bootstrap flow."""
    if config.SYSTEM_LOCKED and not bypass_system_lock:
        raise ValueError("System is locked. New user registration is disabled.")
    if session is None:
        session = get_session()
        close_session = True
    else:
        close_session = False

    try:
        email = email.strip().lower() if email else None
        if email:
            existing = session.query(User).filter(User.email == email).first()
            if existing:
                raise ValueError(f"Email {email} already registered")
        if phone:
            existing = session.query(User).filter(User.phone == phone).first()
            if existing:
                raise ValueError(f"Phone {phone} already registered")
        if telegram_chat_id:
            existing = get_user_by_telegram(telegram_chat_id, session=session)
            if existing:
                raise ValueError(f"Telegram chat {telegram_chat_id} already registered")

        user = User(
            email=email,
            phone=phone,
            display_name=display_name or email or f"User {telegram_chat_id or 'new'}",
            password_hash=password_hash,
            api_key=_generate_api_key(),
            auth_method="password" if password_hash else "telegram" if telegram_chat_id else "api_key",
            telegram_chat_id=str(telegram_chat_id) if telegram_chat_id else None,
            is_admin=False,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        logger.info(
            "Registered user {} (email_present={}, phone_present={}, telegram_hash={})",
            user.id,
            bool(email),
            bool(phone),
            fingerprint_identifier(telegram_chat_id),
        )
        return user
    finally:
        if close_session:
            session.close()


def bind_telegram(user_id: str, chat_id: str, session: Session | None = None) -> bool:
    """Bind a Telegram chat ID to an existing user."""
    if session is None:
        session = get_session()
        close_session = True
    else:
        close_session = False
    try:
        user = session.query(User).filter(User.id == user_id, User.is_active == True).first()
        if not user:
            return False
        user.telegram_chat_id = str(chat_id)
        user.auth_method = "telegram"
        session.commit()
        logger.info("Bound Telegram telegram_hash={} to user {}", fingerprint_identifier(chat_id), user_id)
        return True
    finally:
        if close_session:
            session.close()
