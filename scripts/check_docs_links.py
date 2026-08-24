"""Fail when a Markdown link points at a file that does not exist.

Documentation rots one moved file at a time, and a broken link is the fastest
way for a repository to read as unmaintained — the reader clicks something on
the front page and gets a 404. This walks every tracked Markdown file, resolves
every relative link and image against the file that contains it, and fails on
any target that is not in the tree.

External URLs are deliberately not fetched: network checks are flaky, slow, and
belong to a different kind of gate. Anchors within a page are not validated —
heading slugs are renderer-specific — but a `path#anchor` link still has its
path checked.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]

# [text](target) and ![alt](target). Nested brackets in the text are rare in
# this tree and not worth a full CommonMark parser.
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")

SKIP_PREFIXES = ("http://", "https://", "mailto:", "tel:", "#", "data:")


def tracked_markdown() -> list[Path]:
    output = subprocess.run(
        ["git", "ls-files", "*.md"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [ROOT / line for line in output.split("\n") if line]


def link_targets(path: Path) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    inside_fence = False
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        # Links inside fenced code blocks are examples, not navigation.
        if line.lstrip().startswith("```"):
            inside_fence = not inside_fence
            continue
        if inside_fence:
            continue
        for match in LINK.finditer(line):
            findings.append((number, match.group(1)))
    return findings


def main() -> int:
    failures: list[str] = []
    files = tracked_markdown()
    checked = 0
    for path in files:
        for line_number, raw_target in link_targets(path):
            target = unquote(raw_target.split("#", 1)[0])
            if not target or raw_target.startswith(SKIP_PREFIXES):
                continue
            checked += 1
            resolved = (ROOT / target.lstrip("/")) if target.startswith("/") else (path.parent / target)
            if not resolved.exists():
                relative = path.relative_to(ROOT)
                failures.append(f"{relative}:{line_number} -> {raw_target}")

    if failures:
        print("Documentation link check failed: targets that do not exist:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"Documentation link check passed: {checked} relative links across {len(files)} Markdown files all resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
