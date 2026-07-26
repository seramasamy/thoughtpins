"""Telegram operational and founder-health commands."""

from __future__ import annotations

from thoughtpins.backup import create_backup, list_backups, smoke_restore_backup
from thoughtpins.bot.utils import telegram_user_id, trim_for_telegram
from thoughtpins.founder.ops import build_doctor_report, build_founder_status, build_jobs_report
from thoughtpins.store import get_session


async def cmd_status(update, context) -> None:
    """Show comprehensive system status: mode, health, library sizes, last activity."""
    session = get_session()
    try:
        user_id = telegram_user_id(update, session)
        chat_id = str(update.message.chat_id)
        await update.message.reply_text(build_founder_status(session, user_id=user_id, chat_id=chat_id))
    finally:
        session.close()


async def cmd_doctor(update, context) -> None:
    """Show operational health for founder/local Telegram use."""
    session = get_session()
    try:
        user_id = telegram_user_id(update, session)
        chat_id = str(update.message.chat_id)
        report, _ok = build_doctor_report(session, user_id=user_id, chat_id=chat_id)
        await update.message.reply_text(report)
    finally:
        session.close()


async def cmd_audit(update, context) -> None:
    """Audit memory quality and retrieval infrastructure."""
    from thoughtpins.memory.audit import audit_memory_system, format_audit_report

    session = get_session()
    try:
        user_id = telegram_user_id(update, session)
        report = audit_memory_system(session, user_id=user_id)
        await update.message.reply_text(trim_for_telegram(format_audit_report(report)))
    finally:
        session.close()


async def cmd_jobs(update, context) -> None:
    """Show ingestion job queue and recent failures."""
    session = get_session()
    try:
        user_id = telegram_user_id(update, session)
        await update.message.reply_text(build_jobs_report(session, user_id=user_id))
    finally:
        session.close()


async def cmd_backup(update, context) -> None:
    """Create/send a backup or list recent backups."""
    args = [arg.lower() for arg in (context.args or [])]
    if args and args[0] == "list":
        backups = list_backups(limit=8)
        if not backups:
            await update.message.reply_text("No backups found.")
            return
        lines = ["Recent backups:"]
        for item in backups:
            size_mb = item.size_bytes / (1024 * 1024)
            lines.append(f"- {item.path.name} ({size_mb:.1f} MB)")
        await update.message.reply_text("\n".join(lines))
        return

    if args and args[0] in {"smoke", "test", "verify"}:
        await update.message.reply_text("Creating a backup and restoring it into a scratch directory...")
        smoke_info = smoke_restore_backup(label="telegram-smoke", cleanup=True)
        size_mb = smoke_info.size_bytes / (1024 * 1024)
        await update.message.reply_text(
            "Backup restore smoke passed.\n"
            f"Backup: {smoke_info.backup_path.name} ({size_mb:.1f} MB)\n"
            f"Restored files checked: {smoke_info.restored_files}\n"
            f"Included roots: {', '.join(smoke_info.included_roots) or 'none'}\n"
            "Scratch restore directory was removed."
        )
        return

    await update.message.reply_text("Creating backup...")
    backup_info = create_backup(label="telegram", keep=14)
    size_mb = backup_info.size_bytes / (1024 * 1024)
    if size_mb > 45:
        await update.message.reply_text(
            f"Backup created, but it may be too large for Telegram delivery. Local path:\n{backup_info.path}"
        )
        return
    with open(backup_info.path, "rb") as handle:
        await update.message.reply_document(
            document=handle,
            filename=backup_info.path.name,
            caption=f"Backup created ({size_mb:.1f} MB). Store this somewhere safe.",
        )
