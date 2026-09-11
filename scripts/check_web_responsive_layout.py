"""Static responsive-layout checks for the Thought Pins web app.

The browser screenshot suite is the real proof, but this source-level gate
keeps the app shell honest on machines where Playwright/Vite spawning is
blocked. It focuses on mechanical UX: iPhone/iPad coverage, safe-area fixed
controls, touch targets, overflow containment, and reachable review surfaces.
"""

from __future__ import annotations

import re
from pathlib import Path

from web_assets import StylesheetBundleError, read_stylesheet_bundle

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"

IOS_VIEWPORT_MARKERS = (
    "width: 320",
    "height: 568",
    "width: 375",
    "height: 667",
    "width: 390",
    "height: 844",
    "width: 393",
    "height: 852",
    "width: 402",
    "height: 874",
    "width: 420",
    "height: 912",
    "width: 430",
    "height: 932",
    "width: 440",
    "height: 956",
    "width: 744",
    "height: 1133",
    "width: 834",
    "height: 1112",
    "width: 1024",
    "height: 1366",
)

PHONE_UI_MARKERS = (
    "@media (max-width: 640px)",
    ".mobile-tabbar",
    "grid-template-columns: repeat(5, 1fr)",
    "min-height: 48px",
    "bottom: calc(72px + env(safe-area-inset-bottom))",
    # The tab bar floats clear of the bottom edge, so it offsets itself from the
    # safe area rather than padding its own inside. The guard is unchanged in
    # substance: the bar must still never sit under the home indicator.
    "bottom: max(10px, env(safe-area-inset-bottom))",
    ".mobile-nav-icon",
    ".mobile-nav-label",
    ".chat-nav-glyph",
)

TABLET_UI_MARKERS = (
    "@media (max-width: 860px)",
    "@media (max-width: 1120px)",
    "grid-template-columns: 1fr",
)

CORE_SURFACE_MARKERS = (
    "<ChatView",
    "<MemoryView",
    "<CaptureView",
    "<LibraryView",
    "<EntriesView",
    "<JobsView",
    "<DashboardView",
    "<AccountView",
    "<LegalView",
)

MOBILE_REACHABILITY_MARKERS = (
    "PRIMARY_NAV_ITEMS.map",
    "UTILITY_NAV_ITEMS.map",
    'aria-label="Mobile primary navigation"',
    '"chat"',
    '"memory"',
    '"capture"',
    '"library"',
    '"entries"',
    '"jobs"',
    '"status"',
    '"account"',
    '"legal"',
)


def _check_display_tracking(styles: str, failures: list[str]) -> None:
    """Compact sans headings may track tightly; prose and controls may not."""
    for selector, declarations in re.findall(r"([^{}]+)\{([^{}]*)\}", styles):
        match = re.search(r"letter-spacing:\s*(-[\d.]+)([a-z]+)", declarations)
        if not match:
            continue
        amount, unit = float(match.group(1)), match.group(2)
        if unit != "em" or amount < -0.07:
            failures.append("display tracking must stay within -0.07em of normal")
        if re.search(r"(?<![\w-])(?:body|p|input|textarea|select|button)(?![\w-])", selector):
            failures.append("negative letter spacing is disallowed for prose and controls")


def main() -> int:
    failures: list[str] = []
    styles = _read_css(FRONTEND / "src" / "styles.css", failures)
    app = _read(FRONTEND / "src" / "App.tsx", failures)
    shell = _read(FRONTEND / "src" / "app" / "AppShell.tsx", failures)
    nav = _read(FRONTEND / "src" / "app" / "navigation.tsx", failures)
    review = _read(FRONTEND / "e2e" / "web-review.spec.ts", failures)

    _require_all(styles, PHONE_UI_MARKERS, "phone responsive shell", failures)
    _require_all(styles, TABLET_UI_MARKERS, "tablet responsive shell", failures)
    _require_all(app, CORE_SURFACE_MARKERS, "core app surfaces", failures)
    _require_all(shell + nav, MOBILE_REACHABILITY_MARKERS, "mobile reachable surfaces", failures)
    _require_all(review, IOS_VIEWPORT_MARKERS, "iOS review viewport coverage", failures)

    _check_no_horizontal_risk(styles, failures)
    _check_fixed_controls(styles, failures)
    _check_maintenance_banner_once(styles, failures)
    _check_no_viewport_font_scaling(styles, failures)
    _check_static_fallback_layout(_read(FRONTEND / "static" / "styles.css", failures), failures)

    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        print(f"Web responsive layout check failed: {len(failures)} failure(s).")
        return 1
    print("Web responsive layout check passed.")
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


def _require_all(text: str, markers: tuple[str, ...], label: str, failures: list[str]) -> None:
    for marker in markers:
        if marker not in text:
            failures.append(f"{label} missing marker: {marker}")


def _check_no_horizontal_risk(styles: str, failures: list[str]) -> None:
    required = (
        "min-width: 320px",
        "minmax(0, 1fr)",
        "overflow-wrap: anywhere",
        "overflow-x: auto",
    )
    for marker in required:
        if marker not in styles:
            failures.append(f"overflow containment missing marker: {marker}")
    risky = re.findall(r"grid-template-columns:\s*[^;\n]*minmax\((?:3[3-9]\d|[4-9]\d\d)px", styles)
    if risky:
        failures.append(f"fixed grid columns can overflow phones: {sorted(set(risky))}")


def _check_static_fallback_layout(styles: str, failures: list[str]) -> None:
    required = (
        "@media (max-width: 900px)",
        "@media (max-width: 560px)",
        ".bottom-composer",
        "position: fixed",
        "bottom: calc(12px + env(safe-area-inset-bottom))",
        "padding-bottom: 156px",
        "padding-bottom: 212px",
        "overflow-wrap: anywhere",
        "overflow-x: auto",
    )
    for marker in required:
        if marker not in styles:
            failures.append(f"static fallback responsive layout missing marker: {marker}")


def _check_fixed_controls(styles: str, failures: list[str]) -> None:
    for selector in (".mobile-tabbar", ".global-composer"):
        blocks = _css_blocks(styles, selector)
        if not any("position: fixed" in block for block in blocks):
            failures.append(f"{selector} must be fixed for mobile review usability")
    if ".app-shell.has-global-composer .main" not in styles or "padding-bottom: 196px" not in styles:
        failures.append("main content must reserve space above the mobile global composer and More panel")


def _check_maintenance_banner_once(styles: str, failures: list[str]) -> None:
    if styles.count(".maintenance-banner {") != 1:
        failures.append("maintenance banner style should be global and defined exactly once")
    banner_index = styles.find(".maintenance-banner {")
    phone_index = styles.find("@media (max-width: 640px)")
    if banner_index == -1 or (phone_index != -1 and banner_index > phone_index):
        failures.append("maintenance banner style must not be phone-only")


def _check_no_viewport_font_scaling(styles: str, failures: list[str]) -> None:
    if re.search(r"font-size:\s*[^;]*(vw|vh|vmin|vmax)", styles):
        failures.append("font sizes must not scale directly with viewport units")
    _check_display_tracking(styles, failures)


def _css_blocks(styles: str, selector: str) -> list[str]:
    blocks: list[str] = []
    start = 0
    while True:
        start = styles.find(selector, start)
        if start == -1:
            return blocks
        brace = styles.find("{", start)
        if brace == -1:
            return blocks
        depth = 0
        for index in range(brace, len(styles)):
            if styles[index] == "{":
                depth += 1
            elif styles[index] == "}":
                depth -= 1
                if depth == 0:
                    blocks.append(styles[brace + 1 : index])
                    start = index + 1
                    break
        else:
            return blocks


if __name__ == "__main__":
    raise SystemExit(main())
