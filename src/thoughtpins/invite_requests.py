"""Asking to be let in, without exposing anyone's inbox to the internet.

A `mailto:` link would have put a personal address on a public page and made
every request a direct write into that inbox. Anyone who found the address could
then flood it, and the flooding would land somewhere with no rate limit and real
consequences — Gmail forwarding rules, spam reputation, and an operator who
stops reading their own mail.

So requests are stored instead of sent. The operator is written to at most a
couple of times a day, in a digest, and only ever with a count and a list they
already have in their own database. Nothing about the volume of requests changes
how much mail arrives.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from thoughtpins.config import config
from thoughtpins.db import InviteRequest, User
from thoughtpins.email_delivery import EmailDeliveryError, delivery_configured, send_email

MAX_NOTE_CHARS = 600
PENDING = "pending"
INVITED = "invited"
DECLINED = "declined"


def submit(session: Session, user: User, note: str | None = None) -> InviteRequest:
    """Record a request, or update the note on the one already open.

    One open request per account by design: asking twice is the same ask, and
    letting it become two rows would make the queue a place to shout into.
    """
    cleaned = (note or "").strip()[:MAX_NOTE_CHARS] or None
    existing = (
        session.query(InviteRequest)
        .filter(InviteRequest.user_id == user.id, InviteRequest.status == PENDING)
        .order_by(InviteRequest.created_at_utc.desc())
        .first()
    )
    now = _utcnow()
    if existing is not None:
        if cleaned:
            existing.note = cleaned
        existing.updated_at_utc = now
        session.commit()
        return existing

    record = InviteRequest(user_id=user.id, note=cleaned, status=PENDING, created_at_utc=now, updated_at_utc=now)
    session.add(record)
    session.commit()
    return record


def open_request(session: Session, user: User) -> InviteRequest | None:
    return (
        session.query(InviteRequest)
        .filter(InviteRequest.user_id == user.id, InviteRequest.status == PENDING)
        .order_by(InviteRequest.created_at_utc.desc())
        .first()
    )


def pending_across_tenants(session: Session) -> list[dict[str, Any]]:
    """Every open request, for the operator.

    Walks tenants one at a time rather than issuing a cross-tenant aggregate, so
    the queries stay row-level-security correct with no elevated database role.
    Same approach the usage report takes, and for the same reason.
    """
    from thoughtpins.tenancy import tenant_context

    rows: list[dict[str, Any]] = []
    users = session.query(User.id, User.email, User.created_at_utc).filter(User.deleted_at_utc.is_(None)).all()
    for user_id, email, created in users:
        with tenant_context(user_id):
            record = (
                session.query(InviteRequest)
                .filter(InviteRequest.user_id == user_id, InviteRequest.status == PENDING)
                .order_by(InviteRequest.created_at_utc.desc())
                .first()
            )
            if record is None:
                continue
            rows.append(
                {
                    "request_id": record.id,
                    "user_id": user_id,
                    "email": email or "(no email)",
                    "note": record.note or "",
                    "requested_at_utc": record.created_at_utc.isoformat() if record.created_at_utc else None,
                    "account_created_at_utc": created.isoformat() if created else None,
                    "notified": record.notified_at_utc is not None,
                }
            )
    rows.sort(key=lambda row: row["requested_at_utc"] or "")
    return rows


def maybe_send_digest(session: Session) -> dict[str, Any]:
    """Write to the operator only if it is both useful and allowed right now.

    Two independent limits. A minimum interval means a burst of requests still
    produces one message. A daily ceiling means that even if the interval were
    misconfigured, the number of emails a day cannot climb. Neither depends on
    how many requests arrive, which is the whole point.
    """
    recipient = (config.INVITE_NOTIFY_EMAIL or "").strip()
    if not recipient:
        return {"sent": False, "reason": "no_recipient"}
    if not delivery_configured():
        return {"sent": False, "reason": "email_not_configured"}

    now = _utcnow()
    if _digests_today(session, now) >= max(0, config.INVITE_DIGEST_MAX_PER_DAY):
        return {"sent": False, "reason": "daily_cap_reached"}

    last = _last_notified_at(session)
    interval = timedelta(minutes=max(1, config.INVITE_DIGEST_MIN_INTERVAL_MINUTES))
    if last is not None and now - last < interval:
        return {"sent": False, "reason": "too_soon"}

    unnotified = _unnotified(session)
    if not unnotified:
        return {"sent": False, "reason": "nothing_new"}

    total_pending = len(pending_across_tenants(session))
    subject = f"{config.EMAIL_SUBJECT_PREFIX} {len(unnotified)} new invite request(s)".strip()
    try:
        send_email(
            to=recipient,
            subject=subject,
            html=_html_body(unnotified, total_pending),
            text=_text_body(unnotified, total_pending),
        )
    except EmailDeliveryError as exc:
        # The queue is the record; a failed notification must not lose a request
        # or fail the person's submission.
        logger.error("Invite digest delivery failed: {}", exc)
        return {"sent": False, "reason": "delivery_failed"}

    for record in unnotified:
        record.notified_at_utc = now
    session.commit()
    return {"sent": True, "requests": len(unnotified), "pending_total": total_pending}


def _unnotified(session: Session) -> list[InviteRequest]:
    from thoughtpins.tenancy import tenant_context

    found: list[InviteRequest] = []
    users = session.query(User.id).filter(User.deleted_at_utc.is_(None)).all()
    for (user_id,) in users:
        with tenant_context(user_id):
            found.extend(
                session.query(InviteRequest)
                .filter(
                    InviteRequest.user_id == user_id,
                    InviteRequest.status == PENDING,
                    InviteRequest.notified_at_utc.is_(None),
                )
                .all()
            )
    return found


def _last_notified_at(session: Session) -> datetime | None:
    from thoughtpins.tenancy import tenant_context

    newest: datetime | None = None
    users = session.query(User.id).filter(User.deleted_at_utc.is_(None)).all()
    for (user_id,) in users:
        with tenant_context(user_id):
            value = (
                session.query(InviteRequest.notified_at_utc)
                .filter(InviteRequest.user_id == user_id, InviteRequest.notified_at_utc.isnot(None))
                .order_by(InviteRequest.notified_at_utc.desc())
                .first()
            )
        if value and value[0] and (newest is None or value[0] > newest):
            newest = value[0]
    return newest


def _digests_today(session: Session, now: datetime) -> int:
    """How many digests went out today, counted from the rows themselves.

    Each digest stamps every request it covered with the same timestamp, so the
    number of distinct stamps today is the number of messages sent today. That
    avoids a separate piece of scheduler state that could drift from reality.
    """
    from thoughtpins.tenancy import tenant_context

    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    stamps: set[datetime] = set()
    users = session.query(User.id).filter(User.deleted_at_utc.is_(None)).all()
    for (user_id,) in users:
        with tenant_context(user_id):
            for (value,) in (
                session.query(InviteRequest.notified_at_utc)
                .filter(
                    InviteRequest.user_id == user_id,
                    InviteRequest.notified_at_utc.isnot(None),
                    InviteRequest.notified_at_utc >= start,
                )
                .all()
            ):
                if value:
                    stamps.add(value)
    return len(stamps)


def _text_body(requests: list[InviteRequest], total_pending: int) -> str:
    lines = [
        f"{len(requests)} new invite request(s). {total_pending} pending in total.",
        "",
    ]
    for record in requests:
        lines.append(f"- account {record.user_id}")
        if record.note:
            lines.append(f"  note: {record.note}")
    lines.extend(
        [
            "",
            "Issue a code:  python scripts/create_invite_code.py --uses 1",
            "See the queue: python scripts/invite_requests.py --list",
            "",
            "Addresses are deliberately not included here; look them up in the queue.",
        ]
    )
    return "\n".join(lines)


def _html_body(requests: list[InviteRequest], total_pending: int) -> str:
    items = "".join(
        f"<li><code>{record.user_id}</code>" + (f"<br><em>{_escape(record.note)}</em>" if record.note else "") + "</li>"
        for record in requests
    )
    return (
        f"<p><strong>{len(requests)}</strong> new invite request(s). "
        f"{total_pending} pending in total.</p>"
        f"<ul>{items}</ul>"
        "<p>Issue a code with <code>python scripts/create_invite_code.py --uses 1</code>, "
        "or read the queue with <code>python scripts/invite_requests.py --list</code>.</p>"
    )


def _escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")[:MAX_NOTE_CHARS]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
