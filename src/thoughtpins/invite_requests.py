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
from thoughtpins.db import InviteRequest, OperatorNotification, User
from thoughtpins.email_delivery import EmailDeliveryError, delivery_configured, send_email
from thoughtpins.store import tenant_session

MAX_NOTE_CHARS = 600
PENDING = "pending"
INVITED = "invited"
DECLINED = "declined"
DIGEST_KIND = "invite_digest"


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

    Each tenant is read through its own session. A nested tenant context alone
    would not work: the RLS variable is applied when a transaction begins, so
    switching it inside a request that already has one open changes nothing at
    the database and silently returns the requesting user's rows instead.
    """
    from thoughtpins.store import tenant_session

    rows: list[dict[str, Any]] = []
    users = session.query(User.id, User.email, User.created_at_utc).filter(User.deleted_at_utc.is_(None)).all()
    for user_id, email, created in users:
        with tenant_session(user_id) as scoped:
            record = (
                scoped.query(InviteRequest)
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

    Both are answered from a non-tenant ledger rather than by scanning requests.
    Reading them from tenant-scoped rows looked right and was not: inside a
    request, row-level security limits the scan to the requesting account, so a
    newcomer never saw the previous digest and every arrival sent another email.
    """
    recipient = (config.INVITE_NOTIFY_EMAIL or "").strip()
    if not recipient:
        return {"sent": False, "reason": "no_recipient"}
    if not delivery_configured():
        return {"sent": False, "reason": "email_not_configured"}

    now = _utcnow()
    if _digests_today(session, now) >= max(0, config.INVITE_DIGEST_MAX_PER_DAY):
        return {"sent": False, "reason": "daily_cap_reached"}

    last = _last_digest_at(session)
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

    session.add(OperatorNotification(kind=DIGEST_KIND, sent_at_utc=now, item_count=len(unnotified)))
    for user_id, request_id in unnotified:
        with tenant_session(user_id) as scoped:
            record = scoped.query(InviteRequest).filter(InviteRequest.id == request_id).first()
            if record is not None:
                record.notified_at_utc = now
                scoped.commit()
    session.commit()
    return {"sent": True, "requests": len(unnotified), "pending_total": total_pending}


def _last_digest_at(session: Session) -> datetime | None:
    row = (
        session.query(OperatorNotification.sent_at_utc)
        .filter(OperatorNotification.kind == DIGEST_KIND)
        .order_by(OperatorNotification.sent_at_utc.desc())
        .first()
    )
    return row[0] if row else None


def _unnotified(session: Session) -> list[tuple[str, str]]:
    """(user_id, request_id) for every request not yet in a digest."""
    from thoughtpins.store import tenant_session

    found: list[tuple[str, str]] = []
    users = session.query(User.id).filter(User.deleted_at_utc.is_(None)).all()
    for (user_id,) in users:
        with tenant_session(user_id) as scoped:
            for record in (
                scoped.query(InviteRequest)
                .filter(
                    InviteRequest.user_id == user_id,
                    InviteRequest.status == PENDING,
                    InviteRequest.notified_at_utc.is_(None),
                )
                .all()
            ):
                found.append((user_id, record.id))
    return found


def _digests_today(session: Session, now: datetime) -> int:
    """How many digests have gone out since midnight, from the ledger."""
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        session.query(OperatorNotification)
        .filter(OperatorNotification.kind == DIGEST_KIND, OperatorNotification.sent_at_utc >= start)
        .count()
    )


def _text_body(requests: list[tuple[str, str]], total_pending: int) -> str:
    lines = [f"{len(requests)} new invite request(s). {total_pending} pending in total.", ""]
    for user_id, _request_id in requests:
        lines.append(f"- account {user_id}")
    lines.extend(
        [
            "",
            "Issue a code:  python scripts/create_invite_code.py --uses 1",
            "See the queue: python scripts/invite_requests.py --list",
            "",
            "Addresses and notes are deliberately not included here; read the queue.",
        ]
    )
    return "\n".join(lines)


def _html_body(requests: list[tuple[str, str]], total_pending: int) -> str:
    items = "".join(f"<li><code>{_escape(user_id)}</code></li>" for user_id, _ in requests)
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
