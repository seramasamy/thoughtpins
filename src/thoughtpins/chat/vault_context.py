"""Read-only prompt projection for a user's portable Markdown vault."""

from __future__ import annotations

from loguru import logger

from thoughtpins.chat.context_budget import truncate_middle
from thoughtpins.config import config

VAULT_FILE_CONTEXT_MAX_CHARS = 120_000


def build_vault_file_context(
    user_id: str | None,
    max_chars: int = VAULT_FILE_CONTEXT_MAX_CHARS,
) -> str:
    """Return recent Markdown and text files within a bounded prompt budget."""
    if not user_id:
        return ""

    vault_root = config.vault_path() / user_id
    if not vault_root.exists():
        return ""

    files = [path for path in vault_root.rglob("*") if path.is_file() and path.suffix.lower() in {".md", ".txt"}]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)

    parts: list[str] = []
    used = 0
    for path in files:
        try:
            relative_path = path.relative_to(vault_root).as_posix()
            content = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError as exc:
            logger.warning("Could not read vault context file {}: {}", path, exc)
            continue
        if not content:
            continue
        block = f"### {relative_path}\n{content}\n"
        if used + len(block) > max_chars:
            remaining = max_chars - used
            if remaining > 500:
                parts.append(truncate_middle(block, remaining))
            break
        parts.append(block)
        used += len(block)

    return "\n".join(parts).strip()
