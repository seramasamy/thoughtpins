"""Markdown, YAML frontmatter, and wikilink helpers for Thought Pins vaults."""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
from typing import Any

WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
OBSIDIAN_LINK_NOISE = re.compile(r"[\[\]#^%]")
WIKILINK_LABEL_NOISE = str.maketrans({"[": "(", "]": ")", "|": "-"})
WHITESPACE = re.compile(r"\s+")
FENCE = "```"


def safe_filename(name: str, *, fallback: str = "Untitled", max_length: int = 120) -> str:
    """Return a Windows- and Obsidian-safe filename stem.

    Obsidian stores notes as normal files, so path components must also be safe
    for the host filesystem. The result intentionally avoids brackets and other
    characters that can make wikilinks ambiguous.
    """

    value = unicodedata.normalize("NFKC", str(name or "")).strip()
    value = value.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
    value = ILLEGAL_FILENAME_CHARS.sub(" ", value)
    value = OBSIDIAN_LINK_NOISE.sub(" ", value)
    value = WHITESPACE.sub(" ", value).strip(" .")
    if not value:
        value = fallback
    if value.upper() in WINDOWS_RESERVED_NAMES:
        value = f"{value} note"
    if len(value) > max_length:
        value = value[:max_length].rstrip(" .")
    return value or fallback


def safe_markdown_heading(text: str) -> str:
    value = WHITESPACE.sub(" ", str(text or "")).strip()
    return value or "Untitled"


def note_stem(path: str | PurePosixPath) -> str:
    value = PurePosixPath(str(path).replace("\\", "/"))
    return value.with_suffix("").as_posix()


def wikilink(path: str | PurePosixPath, *, label: str | None = None) -> str:
    target = note_stem(path)
    safe_label = safe_wikilink_label(label)
    if safe_label and safe_label != target:
        return f"[[{target}|{safe_label}]]"
    return f"[[{target}]]"


def safe_wikilink_label(label: str | None) -> str:
    """Return an Obsidian-safe display label for a wikilink alias."""

    if label is None:
        return ""
    return WHITESPACE.sub(" ", str(label).translate(WIKILINK_LABEL_NOISE)).strip()


def markdown_list(items: Sequence[str], *, empty: str = "None recorded.") -> str:
    cleaned = [WHITESPACE.sub(" ", str(item)).strip() for item in items if str(item).strip()]
    if not cleaned:
        return f"- {empty}"
    return "\n".join(f"- {item}" for item in cleaned)


def escape_wikilink_tokens(text: str) -> str:
    """Prevent source text from turning into unintended Obsidian wikilinks."""

    return str(text or "").replace(FENCE, "`` `").replace("[[", r"\[\[").replace("]]", r"\]\]")


def fenced_text(text: str, *, language: str = "text") -> str:
    """Preserve original user/source text without creating accidental wikilinks."""

    body = str(text or "").replace(FENCE, "`` `")
    return f"{FENCE}{language}\n{body}\n{FENCE}"


def frontmatter_block(values: Mapping[str, Any]) -> str:
    lines = ["---"]
    for key, value in values.items():
        lines.extend(_format_yaml_value(str(key), value))
    lines.append("---")
    return "\n".join(lines) + "\n"


def _format_yaml_value(key: str, value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        if not items:
            return [f"{key}: []"]
        lines = [f"{key}:"]
        for item in items:
            lines.append(f"  - {_format_scalar(item)}")
        return lines
    return [f"{key}: {_format_scalar(value)}"]


def _format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    text = str(value)
    if text == "":
        return '""'
    if _can_stay_plain(text):
        return text
    return json.dumps(text, ensure_ascii=False)


def _can_stay_plain(text: str) -> bool:
    if text.strip() != text:
        return False
    if text.lower() in {"null", "true", "false", "yes", "no", "on", "off"}:
        return False
    if any(token in text for token in ("[[", "]]", ": ", "#", "{", "}", "[", "]", "\n", "\r", "\t")):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_./@+\-]+", text))


def parse_frontmatter(markdown: str) -> tuple[dict[str, Any], str]:
    """Parse the simple YAML subset emitted by frontmatter_block.

    This is a validation helper, not a general YAML implementation. It accepts
    JSON-style quoted scalars and block lists, which keeps tests independent of
    an optional PyYAML install while still proving our emitted frontmatter is
    machine-readable.
    """

    if not markdown.startswith("---\n"):
        raise ValueError("missing YAML frontmatter")
    end = markdown.find("\n---", 4)
    if end == -1:
        raise ValueError("unterminated YAML frontmatter")
    raw = markdown[4:end].splitlines()
    body = markdown[end + 5 :].lstrip("\n")
    data: dict[str, Any] = {}
    index = 0
    while index < len(raw):
        line = raw[index]
        if not line.strip():
            index += 1
            continue
        if line.startswith("  ") or ":" not in line:
            raise ValueError(f"invalid frontmatter line: {line}")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value == "":
            items: list[Any] = []
            index += 1
            while index < len(raw) and raw[index].startswith("  - "):
                items.append(_parse_scalar(raw[index][4:].strip()))
                index += 1
            data[key] = items
            continue
        data[key] = [] if value == "[]" else _parse_scalar(value)
        index += 1
    return data, body


def _parse_scalar(value: str) -> Any:
    if value == "null":
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    if value.startswith('"'):
        return json.loads(value)
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


def strip_fenced_blocks(markdown: str) -> str:
    return re.sub(r"```.*?```", "", markdown, flags=re.DOTALL)
