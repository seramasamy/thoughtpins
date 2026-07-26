"""Validate UI-free mobile core scaffolds exist and stay non-visual.

This is not a substitute for SwiftPM or Gradle compilation. It is a local
release gate that catches drift, missing endpoint/model parity, accidental UI
imports, duplicate top-level declarations, and obvious brace/string structure
issues on hosts where native toolchains are not installed.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "mobile/README.md",
    "mobile/ios/ThoughtPinsCore/Package.swift",
    "mobile/ios/ThoughtPinsCore/Sources/ThoughtPinsCore/APIClient.swift",
    "mobile/ios/ThoughtPinsCore/Sources/ThoughtPinsCore/DraftStore.swift",
    "mobile/ios/ThoughtPinsCore/Sources/ThoughtPinsCore/Models.swift",
    "mobile/ios/ThoughtPinsCore/Sources/ThoughtPinsCore/SessionStore.swift",
    "mobile/ios/ThoughtPinsCore/Sources/ThoughtPinsCore/VersionPolicy.swift",
    "mobile/android/thoughtpins-core/build.gradle.kts",
    "mobile/android/thoughtpins-core/src/main/kotlin/com/thoughtpins/core/DraftQueue.kt",
    "mobile/android/thoughtpins-core/src/main/kotlin/com/thoughtpins/core/Models.kt",
    "mobile/android/thoughtpins-core/src/main/kotlin/com/thoughtpins/core/SessionStore.kt",
    "mobile/android/thoughtpins-core/src/main/kotlin/com/thoughtpins/core/ThoughtPinsApiClient.kt",
    "mobile/android/thoughtpins-core/src/main/kotlin/com/thoughtpins/core/VersionPolicy.kt",
]

FORBIDDEN_UI_MARKERS = [
    "import SwiftUI",
    "import UIKit",
    "@Composable",
    "ComponentActivity",
    "AppCompatActivity",
    "setContent",
]

REQUIRED_API_MARKERS = [
    "/v1/client-config",
    "/v1/auth/register",
    "/v1/auth/login",
    "/v1/auth/oauth",
    "/v1/auth/refresh",
    "/v1/auth/logout",
    "/v1/me",
    "/v1/chat",
    "/v1/chat/conversations",
    "/messages",
    "/v1/entries",
    "/v1/jobs",
    "/retry",
    "/cancel",
    "/v1/library",
    "/v1/memory/cards",
    "/v1/uploads",
    "/v1/preferences",
    "/v1/legal/acceptances",
    "/v1/devices",
    "/v1/status",
    "/v1/health/deep",
    "/v1/export",
    "deleteAccount",
    "exportAccount",
    "syncQueuedDrafts",
]

REQUIRED_MODEL_MARKERS = [
    "RegisterResponse",
    "MeResponse",
    "ChatResponse",
    "ChatConversationsPageResponse",
    "ChatMessagesPageResponse",
    "EntriesPageResponse",
    "EntryDeleteResponse",
    "JobsPageResponse",
    "JobResponse",
    "LibraryIngestResponse",
    "LibrarySourceResponse",
    "PreferencesResponse",
    "PreferencesUpdateRequest",
    "DevicesPageResponse",
    "DeviceResponse",
    "AccountExportResponse",
    "AccountDeletionResponse",
    "DraftSyncSummary",
]

PLATFORM_API_FILES = [
    "mobile/ios/ThoughtPinsCore/Sources/ThoughtPinsCore/APIClient.swift",
    "mobile/android/thoughtpins-core/src/main/kotlin/com/thoughtpins/core/ThoughtPinsApiClient.kt",
]

PLATFORM_MODEL_FILES = [
    "mobile/ios/ThoughtPinsCore/Sources/ThoughtPinsCore/Models.swift",
    "mobile/android/thoughtpins-core/src/main/kotlin/com/thoughtpins/core/Models.kt",
]

REQUIRED_CONTRACT_MARKERS = [
    *REQUIRED_API_MARKERS,
    *REQUIRED_MODEL_MARKERS,
    "MemoryCardResponse",
    "UploadIngestResponse",
    "sourceDocuments",
    "askPrompt",
    "obsidianPath",
    "responseStyle",
]

SWIFT_DECL_RE = re.compile(
    r"^(?:(?:public|private|internal|fileprivate)\s+)?(?:final\s+)?(?:actor|struct|enum|class|protocol)\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)
KOTLIN_DECL_RE = re.compile(
    r"^(?:data\s+)?(?:class|interface|object)\s+([A-Za-z_][A-Za-z0-9_]*)|^enum\s+class\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)


def main() -> int:
    problems: list[str] = []
    for rel in REQUIRED_FILES:
        if not (ROOT / rel).is_file():
            problems.append(f"missing required mobile core file: {rel}")

    for rel in REQUIRED_FILES:
        path = ROOT / rel
        if path.suffix not in {".swift", ".kt", ".kts"} or not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN_UI_MARKERS:
            if marker in text:
                problems.append(f"{rel} contains UI marker {marker!r}")
        _check_balanced_delimiters(rel, text, problems)
        _check_duplicate_declarations(rel, text, problems)

    combined = "\n".join((ROOT / rel).read_text(encoding="utf-8") for rel in REQUIRED_FILES if (ROOT / rel).exists())
    for marker in REQUIRED_CONTRACT_MARKERS:
        if marker not in combined:
            problems.append(f"mobile core missing API marker {marker}")

    for rel in PLATFORM_API_FILES:
        text = (ROOT / rel).read_text(encoding="utf-8") if (ROOT / rel).exists() else ""
        for marker in REQUIRED_API_MARKERS:
            if marker not in text:
                problems.append(f"{rel} missing release API marker {marker}")

    for rel in PLATFORM_MODEL_FILES:
        text = (ROOT / rel).read_text(encoding="utf-8") if (ROOT / rel).exists() else ""
        for marker in REQUIRED_MODEL_MARKERS:
            if marker not in text:
                problems.append(f"{rel} missing release model marker {marker}")

    if problems:
        print("Mobile core validation failed:")
        for problem in problems:
            print(f"- {problem}")
        return 1

    print("Mobile core validation passed.")
    return 0


def _check_balanced_delimiters(rel: str, text: str, problems: list[str]) -> None:
    stripped = _strip_comments_and_strings(text)
    pairs = {"}": "{", ")": "(", "]": "["}
    openers = set(pairs.values())
    stack: list[tuple[str, int]] = []
    for index, char in enumerate(stripped):
        if char in openers:
            stack.append((char, index))
        elif char in pairs:
            if not stack or stack[-1][0] != pairs[char]:
                problems.append(f"{rel} has unbalanced delimiter {char!r} near offset {index}")
                return
            stack.pop()
    if stack:
        char, index = stack[-1]
        problems.append(f"{rel} has unclosed delimiter {char!r} near offset {index}")


def _check_duplicate_declarations(rel: str, text: str, problems: list[str]) -> None:
    if rel.endswith(".swift"):
        names = SWIFT_DECL_RE.findall(text)
    elif rel.endswith(".kt"):
        matches = KOTLIN_DECL_RE.findall(text)
        names = [left or right for left, right in matches]
    else:
        return
    counts = Counter(name for name in names if name)
    duplicates = sorted(name for name, count in counts.items() if count > 1)
    if duplicates:
        problems.append(f"{rel} has duplicate top-level declarations: {', '.join(duplicates)}")


def _strip_comments_and_strings(text: str) -> str:
    result: list[str] = []
    i = 0
    in_line_comment = False
    in_block_comment = False
    in_string: str | None = None
    escape = False
    while i < len(text):
        char = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if in_line_comment:
            if char == "\n":
                in_line_comment = False
                result.append(char)
            else:
                result.append(" ")
        elif in_block_comment:
            if char == "*" and nxt == "/":
                in_block_comment = False
                result.extend("  ")
                i += 1
            else:
                result.append("\n" if char == "\n" else " ")
        elif in_string:
            if escape:
                escape = False
                result.append(" ")
            elif char == "\\":
                escape = True
                result.append(" ")
            elif char == in_string:
                in_string = None
                result.append(" ")
            else:
                result.append("\n" if char == "\n" else " ")
        elif char == "/" and nxt == "/":
            in_line_comment = True
            result.extend("  ")
            i += 1
        elif char == "/" and nxt == "*":
            in_block_comment = True
            result.extend("  ")
            i += 1
        elif char in {'"', "'"}:
            in_string = char
            result.append(" ")
        else:
            result.append(char)
        i += 1
    return "".join(result)


if __name__ == "__main__":
    raise SystemExit(main())
