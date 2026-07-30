"""Helpers for inspecting the web app's authored asset graph.

The browser and Vite resolve local CSS imports for us at runtime. Static release
gates need the same effective view so modular stylesheets cannot hide contract
or accessibility regressions from source-level checks.
"""

from __future__ import annotations

import re
from pathlib import Path


class StylesheetBundleError(ValueError):
    """Raised when a local stylesheet graph cannot be resolved safely."""


_IMPORT_PATTERN = re.compile(
    r"^\s*@import\s+(?:url\()?['\"](?P<target>[^'\"]+)['\"]\)?\s*;\s*$",
    re.MULTILINE,
)


def read_stylesheet_bundle(entrypoint: Path) -> str:
    """Return an entrypoint and its local imports in browser evaluation order."""

    entrypoint = entrypoint.resolve()
    allowed_root = entrypoint.parent
    web_root = allowed_root.parent
    visited: set[Path] = set()
    active: list[Path] = []

    def import_path(parent: Path, target: str) -> Path:
        # Imports carry a ?v= cache-busting query so a CDN cannot keep serving a
        # stale sub-stylesheet after a release. That query addresses the browser,
        # not the filesystem, so drop it before resolving to a file.
        target = target.split("?", 1)[0].split("#", 1)[0]
        if target.startswith("/assets/"):
            return web_root / target.removeprefix("/")
        if target.startswith("/"):
            raise StylesheetBundleError(f"unsupported root-relative stylesheet import: {target}")
        return parent / target

    def resolve(path: Path) -> str:
        resolved = path.resolve()
        if not resolved.is_relative_to(allowed_root):
            raise StylesheetBundleError(f"stylesheet import escapes {allowed_root}: {resolved}")
        if resolved in active:
            cycle = " -> ".join(item.name for item in (*active, resolved))
            raise StylesheetBundleError(f"stylesheet import cycle: {cycle}")
        if resolved in visited:
            return ""
        if not resolved.is_file():
            raise StylesheetBundleError(f"missing stylesheet import: {resolved}")

        active.append(resolved)
        source = resolved.read_text(encoding="utf-8-sig", errors="strict")
        chunks: list[str] = []
        cursor = 0
        for match in _IMPORT_PATTERN.finditer(source):
            chunks.append(source[cursor : match.start()])
            target = match.group("target")
            if target.startswith(("http://", "https://", "//")):
                chunks.append(match.group(0))
            else:
                chunks.append(resolve(import_path(resolved.parent, target)))
            cursor = match.end()
        chunks.append(source[cursor:])
        active.pop()
        visited.add(resolved)
        return "\n".join(chunks)

    return resolve(entrypoint)
