"""Founder Telegram operational summaries."""

from __future__ import annotations

import os
import shutil
import time
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from thoughtpins.backup import latest_backup, latest_backup_age_seconds
from thoughtpins.config import config
from thoughtpins.crypto import maybe_decrypt_text
from thoughtpins.db import IngestionJob, RawEntry
from thoughtpins.jobs import worker_health
from thoughtpins.memory.store import MemoryStore


def build_doctor_report(session: Session, *, user_id: str, chat_id: str) -> tuple[str, bool]:
    """Return a plain-text doctor report and whether all critical checks pass."""
    checks: list[tuple[str, str, str]] = []

    _check_db(session, user_id, checks)
    _check_llm(checks)
    _check_article_fetch(checks)
    _check_worker(checks)
    _check_redis(checks)
    _check_backup(checks)
    _check_disk(checks)
    _check_telegram(checks, chat_id)

    ok = all(status in {"ok", "warn"} for _, status, _ in checks)
    lines = ["Thought Pins Doctor", "================", ""]
    for name, status, detail in checks:
        lines.append(f"{status.upper():5} {name}: {detail}")
    return "\n".join(lines), ok


def build_jobs_report(session: Session, *, user_id: str, limit: int = 8) -> str:
    statuses = ["pending", "retry", "queued", "running", "completed", "failed", "dead_letter", "canceled"]
    counts = {
        status: session.query(func.count(IngestionJob.id))
        .filter(IngestionJob.user_id == user_id, IngestionJob.status == status)
        .scalar()
        or 0
        for status in statuses
    }
    recent = (
        session.query(IngestionJob)
        .filter(IngestionJob.user_id == user_id)
        .order_by(IngestionJob.created_at_utc.desc())
        .limit(limit)
        .all()
    )
    lines = ["Ingestion Jobs", "==============", ""]
    lines.append("Counts:")
    for status in statuses:
        lines.append(f"  {status}: {counts[status]}")
    if recent:
        lines.append("")
        lines.append("Recent:")
        for job in recent:
            created = _format_dt(job.created_at_utc)
            entry = f" entry={job.entry_id}" if job.entry_id else ""
            error = f" error={str(job.error)[:80]}" if job.error else ""
            lines.append(f"  {created} {job.status} {job.id}{entry}{error}")
    return "\n".join(lines)


def build_founder_status(session: Session, *, user_id: str, chat_id: str, uptime_seconds: int | None = None) -> str:
    from thoughtpins.bot.disclosure import is_disclosure_mode
    from thoughtpins.chat.personality import get_active_profile

    store = MemoryStore(session, user_id=user_id)
    stats = store.get_stats()
    disclosure = is_disclosure_mode(chat_id)
    last_entry = (
        session.query(RawEntry).filter(RawEntry.user_id == user_id).order_by(RawEntry.created_at_utc.desc()).first()
    )
    private_count = (
        session.query(func.count(RawEntry.id))
        .filter(
            RawEntry.user_id == user_id,
            RawEntry.is_private == True,
        )
        .scalar()
        or 0
    )
    public_count = (
        session.query(func.count(RawEntry.id))
        .filter(
            RawEntry.user_id == user_id,
            RawEntry.is_private == False,
        )
        .scalar()
        or 0
    )
    job_counts = {
        status: session.query(func.count(IngestionJob.id))
        .filter(IngestionJob.user_id == user_id, IngestionJob.status == status)
        .scalar()
        or 0
        for status in ["pending", "retry", "queued", "running", "failed", "dead_letter"]
    }
    latest = latest_backup()
    db_path = config.database_path()
    db_size_mb = os.path.getsize(db_path) / (1024 * 1024) if os.path.exists(db_path) else 0.0
    vault_files = len(list(config.vault_path().rglob("*.md"))) if config.vault_path().exists() else 0

    lines = [
        "Thought Pins Status",
        "=================",
        "",
        f"Mode: {'CONFIDENTIAL' if disclosure else 'STANDARD'}",
        f"Personality: {get_active_profile(chat_id).name}",
        f"Environment: {config.ENVIRONMENT}",
        f"AI processing: {'configured' if config.LLM_API_KEY else 'missing key'}",
    ]
    if uptime_seconds is not None:
        lines.append(f"Uptime: {_format_duration(uptime_seconds)}")

    lines.extend(
        [
            "",
            "Library:",
            f"  Standard entries: {public_count}",
            f"  Private entries: {private_count}",
            f"  Entities: {stats['entities']}",
            f"  Memories: {stats['memories']}",
            f"  Relationships: {stats['relationships']}",
            f"  Events: {stats['events']}",
            f"  Action items: {stats['action_items']}",
            f"  Vault files: {vault_files}",
            f"  Database size: {db_size_mb:.1f} MB",
            "",
            "Jobs:",
            f"  Pending/retry/running: {job_counts['pending']}/{job_counts['retry']}/{job_counts['running']}",
            f"  Failed/dead-letter: {job_counts['failed']}/{job_counts['dead_letter']}",
            "",
            "Backup:",
            f"  Latest: {_format_dt(latest.created_at_utc) if latest else 'none'}",
        ]
    )
    if last_entry:
        age = _age_text(last_entry.created_at_utc)
        text = maybe_decrypt_text(last_entry.raw_text or "")[:80].replace("\n", " ")
        lines.extend(["", f"Last entry: {age}", f"  {text}"])
    else:
        lines.extend(["", "Last entry: none"])
    return "\n".join(lines)


def _check_db(session: Session, user_id: str, checks: list[tuple[str, str, str]]) -> None:
    try:
        count = session.query(func.count(RawEntry.id)).filter(RawEntry.user_id == user_id).scalar() or 0
        checks.append(("database", "ok", f"reachable, {count} entries"))
    except Exception as e:
        checks.append(("database", "error", str(e)[:160]))


def _check_llm(checks: list[tuple[str, str, str]]) -> None:
    if not config.LLM_API_KEY:
        checks.append(("llm", "error", "LLM API key is missing"))
        return
    detail = "configured endpoint" if config.LLM_BASE_URL else "configured"
    checks.append(("llm", "ok", detail))


def _check_article_fetch(checks: list[tuple[str, str, str]]) -> None:
    from thoughtpins.library import article_fetch_health

    health = article_fetch_health()
    status = "warn" if health.get("status") == "warn" else "ok"
    providers = ",".join(health.get("providers", [])) or "local"
    paid_ready = ",".join(health.get("paid_fallbacks_ready", [])) or "none"
    jina_key = "key" if health.get("jina", {}).get("api_key_present") else "keyless"
    detail = f"providers={providers}; jina={jina_key}; paid_ready={paid_ready}"
    if health.get("unknown_providers"):
        detail += f"; unknown={','.join(health['unknown_providers'])}"
    checks.append(("article_fetch", status, detail))


def _check_worker(checks: list[tuple[str, str, str]]) -> None:
    health = worker_health()
    status = "ok" if health.get("status") in {"ok", "configured"} else "error"
    detail = ", ".join(f"{k}={v}" for k, v in health.items() if k != "status")
    checks.append(("worker", status, detail or str(health)))


def _check_redis(checks: list[tuple[str, str, str]]) -> None:
    if not config.REDIS_URL:
        checks.append(("redis", "warn", "not configured; ok for local founder thread mode"))
        return
    try:
        from redis import Redis

        client = Redis.from_url(config.REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
        client.ping()
        checks.append(("redis", "ok", "reachable"))
    except Exception as e:
        checks.append(("redis", "warn", str(e)[:160]))


def _check_backup(checks: list[tuple[str, str, str]]) -> None:
    age = latest_backup_age_seconds()
    if age is None:
        checks.append(("backup", "warn", "no local backups found"))
        return
    status = "ok" if age <= 36 * 3600 else "warn"
    checks.append(("backup", status, f"latest {_format_duration(age)} ago"))


def _check_disk(checks: list[tuple[str, str, str]]) -> None:
    try:
        usage = shutil.disk_usage(config.resolve_path("."))
        free_gb = usage.free / (1024**3)
        status = "ok" if free_gb >= 2 else "warn"
        checks.append(("disk", status, f"{free_gb:.1f} GB free"))
    except Exception as e:
        checks.append(("disk", "warn", str(e)[:160]))


def _check_telegram(checks: list[tuple[str, str, str]], chat_id: str) -> None:
    if not config.TELEGRAM_BOT_TOKEN:
        checks.append(("telegram", "error", "bot token missing"))
        return
    mode = "test mode" if config.TELEGRAM_TEST_MODE else "allowlist"
    checks.append(("telegram", "ok", f"{mode}, chat={chat_id}"))


def _format_dt(value: datetime | None) -> str:
    if not value:
        return "unknown"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _age_text(value: datetime | None) -> str:
    if not value:
        return "unknown"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    age = int(time.time() - value.timestamp())
    return f"{_format_duration(age)} ago"
