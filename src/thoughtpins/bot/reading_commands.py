"""Telegram reading-library commands."""

from __future__ import annotations

from loguru import logger

from thoughtpins.bot.utils import parse_limit, telegram_user_id, trim_for_telegram
from thoughtpins.library import (
    extract_urls,
    find_document,
    ingest_document_text,
    ingest_url,
    list_documents,
)
from thoughtpins.store import get_session


def _strip_library_prefix(text: str) -> str:
    lowered = text.lower().lstrip()
    for prefix in ("read:", "article:", "source:", "doc:", "document:"):
        if lowered.startswith(prefix):
            return text[text.lower().find(prefix) + len(prefix) :].strip()
    return text.strip()


async def ingest_library_message(update, text: str) -> None:
    """Ingest a URL or pasted source text into the reading/document library."""
    body = _strip_library_prefix(text)
    if not body:
        await update.message.reply_text("Usage: /read <article URL or pasted article/document text>")
        return

    await update.message.chat.send_action("typing")
    session = get_session()
    try:
        user_id = telegram_user_id(update, session)
        urls = extract_urls(body)
        if urls:
            note = body
            for url in urls:
                note = note.replace(url, "").strip()
            result = ingest_url(
                session,
                urls[0],
                user_id=user_id,
                telegram_chat_id=str(update.message.chat_id),
                note=note,
                defer_vector_index=True,
            )
        else:
            title = body.splitlines()[0].strip()[:120] if "\n" in body else ""
            result = ingest_document_text(
                session,
                body,
                user_id=user_id,
                telegram_chat_id=str(update.message.chat_id),
                source_type="text",
                title=title,
                defer_vector_index=True,
            )

        duplicate = "Already saved. " if result.duplicate else ""
        if result.status == "needs_text":
            await update.message.reply_text(
                f"{duplicate}Saved source link: {result.title}\n"
                "The article was not publicly readable and no authorized open copy was available. "
                "I can still remember its title, link, and any notes you add."
            )
            return

        await update.message.reply_text(
            f"{duplicate}Saved source: {result.title}\n"
            f"{result.chunks} searchable {'section is' if result.chunks == 1 else 'sections are'} now available in your reading memory."
        )
    except Exception as exc:
        logger.error("Library ingest failed: {}", exc)
        await update.message.reply_text(
            "I could not save that source. Check the link or add a short note about what you want to remember."
        )
    finally:
        session.close()


async def cmd_read(update, context) -> None:
    """Save an article URL or pasted document text into reading memory."""
    raw_text = getattr(update.message, "text", "") or ""
    if raw_text.startswith("/"):
        parts = raw_text.split(maxsplit=1)
        text = parts[1] if len(parts) > 1 else ""
    else:
        text = " ".join(context.args) if context.args else ""
    await ingest_library_message(update, text)


async def cmd_library(update, context) -> None:
    """List saved articles and documents."""
    limit = parse_limit(context.args or [], default=15, maximum=50)
    session = get_session()
    try:
        user_id = telegram_user_id(update, session)
        docs = list_documents(session, user_id, limit=limit)
        if not docs:
            await update.message.reply_text("No saved articles or documents yet. Use /read <url or text>.")
            return
        lines = [f"Reading memory ({len(docs)} shown):"]
        for doc in docs:
            url = f" - {doc.source_url}" if doc.source_url else ""
            lines.append(f"- {doc.title} [{doc.source_type}, {doc.status}]{url}")
        await update.message.reply_text(trim_for_telegram("\n".join(lines)))
    finally:
        session.close()


async def cmd_source(update, context) -> None:
    """Show one saved source with summary and first excerpts."""
    ref = " ".join(context.args) if context.args else ""
    if not ref:
        await update.message.reply_text("Usage: /source <id or title>")
        return
    session = get_session()
    try:
        user_id = telegram_user_id(update, session)
        doc = find_document(session, user_id, ref)
        if not doc:
            await update.message.reply_text(f"No saved source found for '{ref}'.")
            return
        lines = [
            f"Source: {doc.title}",
            f"Type: {doc.source_type}",
            f"Status: {doc.status}",
        ]
        original_url = doc.canonical_url or doc.source_url or doc.original_url
        if original_url:
            lines.append(f"Original: {original_url}")
        if doc.status != "processed":
            lines.append("Full text is not available yet. Add article text you can access for complete recall.")
        if doc.summary:
            lines.extend(["", "Summary:", doc.summary[:1000]])
        chunks = sorted(doc.chunks, key=lambda chunk: chunk.chunk_index)
        if chunks:
            lines.append("")
            lines.append("First excerpts:")
            for chunk in chunks[:3]:
                lines.append(f"- [{chunk.chunk_index + 1}] {chunk.text[:350]}")
        await update.message.reply_text(trim_for_telegram("\n".join(lines)))
    finally:
        session.close()
