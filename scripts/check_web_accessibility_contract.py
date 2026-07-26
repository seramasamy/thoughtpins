"""Static accessibility and store-review UX checks for the Thought Pins web app.

This is not a replacement for axe or real-device testing. It is a cheap release
gate for review-critical basics that can be checked without launching a browser:
keyboard focus, labeled icon buttons, live status announcements, account/data
controls, legal links, and public UI hygiene.
"""

from __future__ import annotations

import re
from pathlib import Path

from web_assets import StylesheetBundleError, read_stylesheet_bundle

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def main() -> int:
    failures: list[str] = []
    src_styles = _read_css(FRONTEND / "src" / "styles.css", failures)
    static_styles = _read(FRONTEND / "static" / "styles.css", failures)
    shell = _read(FRONTEND / "src" / "app" / "AppShell.tsx", failures)
    ui = _read(FRONTEND / "src" / "components" / "ui.tsx", failures)
    chat = _read(FRONTEND / "src" / "features" / "chat" / "ChatView.tsx", failures)
    account = _read(FRONTEND / "src" / "features" / "account" / "AccountView.tsx", failures)
    legal = _read(FRONTEND / "src" / "features" / "legal" / "LegalView.tsx", failures)
    static_app = _read(FRONTEND / "static" / "app.js", failures)

    _check_focus_visible(src_styles, "React CSS", failures)
    _check_focus_visible(static_styles, "static fallback CSS", failures)
    _check_long_text_resilience(src_styles, "React CSS", failures)
    _check_long_text_resilience(static_styles, "static fallback CSS", failures)
    _check_icon_button_labels(FRONTEND / "src", failures)
    _check_static_icon_button_labels(static_app, failures)
    _check_live_regions(ui, shell, chat, static_app, failures)
    _check_account_and_legal_controls(account, legal, static_app, failures)
    _check_public_ui_hygiene(shell + chat + account + legal + static_app, failures)

    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        print(f"Web accessibility contract check failed: {len(failures)} failure(s).")
        return 1
    print("Web accessibility contract check passed.")
    return 0


def _read(path: Path, failures: list[str]) -> str:
    if not path.is_file():
        failures.append(f"missing file: {path.relative_to(ROOT)}")
        return ""
    return path.read_text(encoding="utf-8-sig", errors="ignore")


def _read_css(path: Path, failures: list[str]) -> str:
    try:
        return read_stylesheet_bundle(path)
    except (OSError, UnicodeError, StylesheetBundleError) as exc:
        failures.append(f"could not resolve stylesheet bundle {path.relative_to(ROOT)}: {exc}")
        return ""


def _check_focus_visible(styles: str, label: str, failures: list[str]) -> None:
    required = (":focus-visible", "outline-offset", "button:focus-visible")
    for marker in required:
        if marker not in styles:
            failures.append(f"{label} missing keyboard focus marker: {marker}")


def _check_long_text_resilience(styles: str, label: str, failures: list[str]) -> None:
    for marker in ("overflow-wrap: anywhere", "minmax(0, 1fr)", "min-width: 0"):
        if marker not in styles:
            failures.append(f"{label} missing long-content guard: {marker}")
    if "word-break: break-all" in styles:
        failures.append(f"{label} uses word-break: break-all; prefer readable overflow wrapping")


def _check_icon_button_labels(root: Path, failures: list[str]) -> None:
    for path in sorted(root.rglob("*.tsx")):
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
        for start in [match.start() for match in re.finditer(r"<IconButton\b", text)]:
            end = _jsx_component_end(text, start, "IconButton")
            block = text[start:end]
            if "aria-label=" not in block or "title=" not in block:
                line = text.count("\n", 0, start) + 1
                failures.append(f"{path.relative_to(ROOT)}:{line} IconButton must include aria-label and title")


def _jsx_component_end(text: str, start: int, name: str) -> int:
    close = text.find(f"</{name}>", start)
    if close != -1:
        return close + len(name) + 3
    line_end = text.find("\n", start)
    return len(text) if line_end == -1 else line_end


def _check_static_icon_button_labels(static_app: str, failures: list[str]) -> None:
    pattern = r"<button\b(?P<attrs>[^>]*class=\"[^\"]*icon-button[^\"]*\"[^>]*)>"
    for match in re.finditer(pattern, static_app):
        attrs = match.group("attrs")
        if "aria-label=" not in attrs and "title=" not in attrs:
            line = static_app.count("\n", 0, match.start()) + 1
            failures.append(f"frontend/static/app.js:{line} static icon button must include aria-label or title")


def _check_live_regions(ui: str, shell: str, chat: str, static_app: str, failures: list[str]) -> None:
    required_pairs = (
        ("React notices", ui, 'role="status"'),
        ("React maintenance banner", shell, 'role="status"'),
        ("React chat thread", chat, 'aria-live="polite"'),
        ("static notice", static_app, 'class="notice ${escapeHtml(state.notice.tone)}" role="status"'),
        ("static maintenance banner", static_app, 'class="maintenance-banner" role="status"'),
        ("static chat thread", static_app, 'class="chat-thread" aria-live="polite"'),
    )
    for label, text, marker in required_pairs:
        if marker not in text:
            failures.append(f"{label} missing live/status marker: {marker}")


def _check_account_and_legal_controls(account: str, legal: str, static_app: str, failures: list[str]) -> None:
    react_account_markers = (
        "api.exportAccount",
        "api.deleteAccount",
        'confirm !== "DELETE"',
        "localMode || confirm",
        "api.registerDevice",
        "api.revokeDevice",
    )
    legal_markers = (
        "privacy_policy_url",
        "terms_url",
        "support_url",
        "account_deletion_url",
        "ai_disclosure_url",
        "createSafetyReport",
    )
    static_markers = (
        "/v1/export",
        "/v1/me",
        "Delete Account Data",
        "account_deletion_url",
        "ai_disclosure_url",
    )
    for marker in react_account_markers:
        if marker not in account:
            failures.append(f"React account surface missing marker: {marker}")
    for marker in legal_markers:
        if marker not in legal:
            failures.append(f"React legal surface missing marker: {marker}")
    for marker in static_markers:
        if marker not in static_app:
            failures.append(f"static fallback account/legal surface missing marker: {marker}")


def _check_public_ui_hygiene(text: str, failures: list[str]) -> None:
    forbidden_visible_copy = (
        "local " + "founder mode",
        "founder " + "testing",
        "telegram " + "founder",
        "dark" + "boy",
        "deep" + "seek",
    )
    lowered = text.lower()
    for marker in forbidden_visible_copy:
        if marker in lowered:
            failures.append(f"public UI exposes review-risk copy: {marker!r}")


if __name__ == "__main__":
    raise SystemExit(main())
