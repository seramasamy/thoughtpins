"""Optional plugin-free Obsidian defaults for exported Thought Pins vaults."""

from __future__ import annotations

import json
from pathlib import Path

APP_DEFAULTS: dict[str, object] = {
    "attachmentFolderPath": "Attachments",
    "alwaysUpdateLinks": True,
    "newFileLocation": "current",
    "promptDelete": False,
    "readableLineLength": True,
    "showLineNumber": False,
}

APPEARANCE_DEFAULTS: dict[str, object] = {
    "accentColor": "#e8612b",
    "cssTheme": "",
    "enabledCssSnippets": [],
    "nativeMenus": True,
    "theme": "obsidian",
}

CORE_PLUGIN_DEFAULTS: list[str] = [
    "file-explorer",
    "global-search",
    "switcher",
    "graph",
    "canvas",
    "bases",
    "backlink",
    "outgoing-link",
    "tag-pane",
    "page-preview",
    "daily-notes",
    "templates",
    "note-composer",
    "command-palette",
    "editor-status",
    "bookmarks",
    "properties",
]

DAILY_NOTES_DEFAULTS: dict[str, object] = {
    "folder": "Journal",
    "format": "YYYY/MM/YYYY-MM-DD",
}


def write_obsidian_defaults(vault: str | Path) -> list[str]:
    """Write safe, plugin-free Obsidian defaults and return relative files written.

    The exporter does not create `.obsidian` by default because many users sync
    their own Obsidian settings. This helper is opt-in and only writes JSON files
    that Obsidian can ignore or merge without requiring community plugins.
    """

    root = Path(vault)
    config_dir = root / ".obsidian"
    config_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "app.json": APP_DEFAULTS,
        "appearance.json": APPEARANCE_DEFAULTS,
        "core-plugins.json": CORE_PLUGIN_DEFAULTS,
        "daily-notes.json": DAILY_NOTES_DEFAULTS,
    }
    written: list[str] = []
    for name, payload in files.items():
        path = config_dir / name
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(path.relative_to(root).as_posix())
    return written
