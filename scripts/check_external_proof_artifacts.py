"""Validate portable closed-beta proof artifacts from a capable host.

This checker lets a Docker/browser-capable machine produce handoff evidence and
lets the normal local packet verify that evidence without needing to rerun those
heavy checks on the current host. It validates two artifacts:

- `reports/compose-rehearsal-*.json` from `scripts/run_compose_rehearsal.ps1` or `scripts/run_compose_rehearsal.py`
- `reports/playwright-web-smoke.json` from `cd frontend && npm run smoke:web`
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import shutil
import struct
import zlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"

COMPOSE_REQUIRED_STEPS = {
    "docker daemon",
    "docker compose config",
    "start compose services",
    "wait for API health",
    "web smoke",
    "production parity with live API and RLS",
    "HTTP API smoke",
    "backup restore smoke",
}
COMPOSE_REQUIRED_CHECK_MARKERS = {
    "docker compose config",
    "production_parity_check.py --strict-api --with-postgres-rls",
    "smoke_api.py",
    "smoke_restore_backup.py",
}
PLAYWRIGHT_REQUIRED_TITLES = {
    "local app shell is responsive and navigable on desktop",
    "local app shell is responsive and navigable on tablet",
    "local app shell is responsive and navigable on mobile",
    "local app shell is responsive and navigable on iPhone 17 / 17 Pro",
    "local app shell is responsive and navigable on iPhone Air",
    "local app shell is responsive and navigable on iPhone 17 Pro Max",
    "auth flow exposes login and registration without founder controls",
    "library ingestion supports article links and file uploads",
    "memory cards present provenance without internal vault paths",
    "account export and deletion controls work",
    "maintenance mode keeps the web app usable and pauses chat writes",
    "offline config failure shows a useful review-safe message",
    "review surface has no serious automated accessibility violations",
}
PLAYWRIGHT_REQUIRED_SCREENSHOTS = {
    "desktop-review-shell.png": (1200, 800),
    "tablet-review-shell.png": (760, 900),
    "mobile-review-shell.png": (360, 700),
    "iphone17-pro-review-shell.png": (390, 820),
    "iphone-air-review-shell.png": (400, 860),
    "iphone17-pro-max-review-shell.png": (420, 900),
    "auth-review.png": (1000, 650),
    "library-ingestion-review.png": (1000, 650),
    "memory-card-review.png": (1000, 650),
    "account-export-delete-review.png": (1000, 650),
    "maintenance-review.png": (1000, 650),
    "offline-review.png": (1000, 650),
}
PLAYWRIGHT_REQUIRED_SCREENSHOT_SCENARIOS = {
    "desktop-review-shell.png": "desktop responsive app shell",
    "tablet-review-shell.png": "tablet responsive app shell",
    "mobile-review-shell.png": "mobile responsive app shell",
    "iphone17-pro-review-shell.png": "iPhone 17 class responsive app shell",
    "iphone-air-review-shell.png": "iPhone Air responsive app shell",
    "iphone17-pro-max-review-shell.png": "iPhone 17 Pro Max responsive app shell",
    "auth-review.png": "auth login and registration without founder controls",
    "library-ingestion-review.png": "library article link and file upload ingestion",
    "memory-card-review.png": "memory card provenance and Obsidian vault paths",
    "account-export-delete-review.png": "account export and deletion controls",
    "maintenance-review.png": "maintenance mode pauses writes with a useful message",
    "offline-review.png": "offline backend configuration message",
}
PLAYWRIGHT_PROOF_MANIFEST = "web-proof-manifest.json"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
BAD_PLAYWRIGHT_STATUSES = {"failed", "timedout", "interrupted"}
SECRET_PATTERNS = [
    re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bjina_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bfc-[A-Za-z0-9]{16,}\b"),
    re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._-]+"),
    re.compile(r"(?i)((?:api[_-]?key|auth[_-]?token|bot[_-]?token|password|jwt[_-]?secret)\s*[=:]\s*)[^\s,;'\"]+"),
    re.compile(r"(postgresql(?:\+psycopg2)?://)([^:@/]+):([^@/]+)@"),
    re.compile(r"(redis://)(:[^@/]+@)"),
]


@dataclass
class ProofResult:
    name: str
    status: str
    path: str = ""
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProofReport:
    app: str = "Thought Pins"
    generated_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "running"
    results: list[ProofResult] = field(default_factory=list)
    report_path: str = ""


@dataclass(frozen=True)
class PngInspection:
    width: int
    height: int
    luma_min: int
    luma_max: int
    distinct_samples: int

    @property
    def luma_range(self) -> int:
        return self.luma_max - self.luma_min


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate closed-beta external proof artifacts.")
    parser.add_argument("--compose-report", default="", help="Path to compose rehearsal JSON.")
    parser.add_argument("--playwright-report", default="", help="Path to Playwright JSON reporter output.")
    parser.add_argument(
        "--web-smoke-dir", default=str(REPORTS / "web-smoke"), help="Directory containing review screenshots."
    )
    parser.add_argument(
        "--latest", action="store_true", help="Use the latest reports/* proof artifacts when paths are omitted."
    )
    parser.add_argument(
        "--require-both", action="store_true", help="Fail unless both compose and Playwright proof are present."
    )
    parser.add_argument(
        "--max-age-hours", type=float, default=168.0, help="Maximum accepted artifact age; <=0 disables age checks."
    )
    parser.add_argument(
        "--self-test", action="store_true", help="Validate synthetic proof artifacts without Docker or a browser."
    )
    parser.add_argument("--json", action="store_true", help="Print the machine-readable validation report.")
    args = parser.parse_args()

    if args.self_test:
        return _run_self_test(print_json=args.json)

    compose = _resolve_path(args.compose_report)
    playwright = _resolve_path(args.playwright_report)
    if args.latest:
        compose = compose or _latest("compose-rehearsal-*.json")
        playwright = playwright or _latest("playwright-web-smoke*.json") or _latest("playwright-*.json")

    report = ProofReport()
    if compose:
        report.results.append(validate_compose_report(compose, max_age_hours=args.max_age_hours))
    elif args.require_both:
        report.results.append(ProofResult("compose rehearsal proof", "failed", reason="compose report is required"))

    if playwright:
        report.results.append(
            validate_playwright_report(playwright, Path(args.web_smoke_dir), max_age_hours=args.max_age_hours)
        )
    elif args.require_both:
        report.results.append(ProofResult("playwright web proof", "failed", reason="playwright report is required"))

    if not report.results:
        report.results.append(
            ProofResult(
                "external proof artifacts",
                "failed",
                reason="no proof artifacts supplied; pass --compose-report/--playwright-report or --latest",
            )
        )

    return _finish(report, print_json=args.json)


def validate_compose_report(path: Path, *, max_age_hours: float = 168.0) -> ProofResult:
    failures: list[str] = []
    data = _load_json(path, failures)
    if data:
        _check_no_secrets(path, failures)
        if data.get("app") != "Thought Pins":
            failures.append("compose report app must be Thought Pins")
        if data.get("status") != "passed":
            failures.append(f"compose report status must be passed, got {data.get('status')!r}")
        _check_fresh(data.get("generated_at_utc") or data.get("finished_at_utc"), max_age_hours, failures)

        steps = {str(step.get("name")): step for step in data.get("steps") or []}
        missing = sorted(COMPOSE_REQUIRED_STEPS - steps.keys())
        if missing:
            failures.append(f"compose report missing required steps: {missing}")
        for name in COMPOSE_REQUIRED_STEPS & steps.keys():
            if steps[name].get("status") != "passed":
                failures.append(f"compose step {name!r} did not pass")

        checks = "\n".join(str(item) for item in data.get("checks") or [])
        for marker in COMPOSE_REQUIRED_CHECK_MARKERS:
            if marker not in checks:
                failures.append(f"compose checks missing marker: {marker}")

        if data.get("keep_running") is not True and data.get("stopped_compose_project") is not True:
            failures.append("compose project must be stopped unless keep_running is true")
        if not str(data.get("base_url") or "").startswith("http"):
            failures.append("compose report must include base_url")

    return ProofResult(
        "compose rehearsal proof",
        "failed" if failures else "passed",
        path=_relative(path),
        reason="; ".join(failures),
        details={"required_steps": sorted(COMPOSE_REQUIRED_STEPS)},
    )


def validate_playwright_report(path: Path, screenshot_dir: Path, *, max_age_hours: float = 168.0) -> ProofResult:
    failures: list[str] = []
    data = _load_json(path, failures)
    if data:
        _check_no_secrets(path, failures)
        _check_fresh(data.get("generated_at_utc"), max_age_hours, failures, required=False)
        titles = _collect_values(data, "title")
        statuses = [str(item).lower() for item in _collect_values(data, "status")]
        raw_stats = data.get("stats")
        stats: dict[str, Any] = raw_stats if isinstance(raw_stats, dict) else {}

        missing_titles = sorted(title for title in PLAYWRIGHT_REQUIRED_TITLES if title not in titles)
        if missing_titles:
            failures.append(f"playwright report missing required tests: {missing_titles}")

        bad_statuses = sorted({status for status in statuses if status in BAD_PLAYWRIGHT_STATUSES})
        if bad_statuses:
            failures.append(f"playwright report has failed statuses: {bad_statuses}")

        unexpected = _safe_int(stats.get("unexpected"))
        skipped = _safe_int(stats.get("skipped"))
        expected = _safe_int(stats.get("expected"))
        passed_results = sum(1 for status in statuses if status == "passed")
        if unexpected:
            failures.append(f"playwright report has {unexpected} unexpected test(s)")
        if skipped:
            failures.append(f"playwright report has {skipped} skipped test(s)")
        if max(expected, passed_results) < len(PLAYWRIGHT_REQUIRED_TITLES):
            failures.append("playwright report does not prove all required web review tests passed")

        _check_screenshots(screenshot_dir, failures)
        _check_web_proof_manifest(screenshot_dir, max_age_hours, failures)

    return ProofResult(
        "playwright web proof",
        "failed" if failures else "passed",
        path=_relative(path),
        reason="; ".join(failures),
        details={
            "required_tests": sorted(PLAYWRIGHT_REQUIRED_TITLES),
            "screenshot_dir": _relative(screenshot_dir),
            "proof_manifest": _relative(screenshot_dir / PLAYWRIGHT_PROOF_MANIFEST),
        },
    )


def _run_self_test(*, print_json: bool) -> int:
    tmp = ROOT / ".tmp" / f"external-proof-self-test-{secrets.token_hex(6)}"
    try:
        tmp.mkdir(parents=True, exist_ok=False)
        compose = tmp / "compose-rehearsal-self-test.json"
        playwright = tmp / "playwright-web-smoke.json"
        screenshots = tmp / "web-smoke"
        screenshots.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        compose.write_text(json.dumps(_self_test_compose(now), indent=2), encoding="utf-8")
        playwright.write_text(json.dumps(_self_test_playwright(now), indent=2), encoding="utf-8")
        for name, dimensions in PLAYWRIGHT_REQUIRED_SCREENSHOTS.items():
            (screenshots / name).write_bytes(_minimal_png(*dimensions))
        _write_self_test_web_proof_manifest(screenshots, now)
        report = ProofReport(
            results=[
                validate_compose_report(compose),
                validate_playwright_report(playwright, screenshots),
            ]
        )
        return _finish(report, print_json=print_json, write_report=False)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _self_test_compose(now: str) -> dict[str, Any]:
    return {
        "app": "Thought Pins",
        "generated_at_utc": now,
        "status": "passed",
        "project_name": "thoughtpins-rehearsal",
        "keep_running": False,
        "stopped_compose_project": True,
        "base_url": "http://127.0.0.1:8420",
        "checks": sorted(COMPOSE_REQUIRED_CHECK_MARKERS),
        "steps": [{"name": name, "status": "passed", "seconds": 0.1} for name in sorted(COMPOSE_REQUIRED_STEPS)],
    }


def _write_self_test_web_proof_manifest(screenshot_dir: Path, now: str) -> None:
    screenshots = []
    for filename, dimensions in sorted(PLAYWRIGHT_REQUIRED_SCREENSHOTS.items()):
        min_width, min_height = dimensions
        screenshots.append(
            {
                "file": filename,
                "scenario": PLAYWRIGHT_REQUIRED_SCREENSHOT_SCENARIOS[filename],
                "viewport": _self_test_viewport(filename),
                "min_width": min_width,
                "min_height": min_height,
            }
        )
    (screenshot_dir / PLAYWRIGHT_PROOF_MANIFEST).write_text(
        json.dumps({"app": "Thought Pins", "generated_at_utc": now, "screenshots": screenshots}, indent=2),
        encoding="utf-8",
    )


def _self_test_viewport(filename: str) -> str:
    if filename.startswith("desktop-"):
        return "desktop"
    if filename.startswith("tablet-"):
        return "tablet"
    if filename.startswith("mobile-"):
        return "mobile"
    if filename.startswith("iphone17-pro-max-"):
        return "iPhone 17 Pro Max"
    if filename.startswith("iphone17-pro-"):
        return "iPhone 17 / 17 Pro"
    if filename.startswith("iphone-air-"):
        return "iPhone Air"
    return "desktop-default"


def _self_test_playwright(now: str) -> dict[str, Any]:
    return {
        "generated_at_utc": now,
        "stats": {"expected": len(PLAYWRIGHT_REQUIRED_TITLES), "unexpected": 0, "skipped": 0},
        "suites": [
            {
                "title": "Thought Pins web review smoke",
                "specs": [
                    {"title": title, "tests": [{"status": "expected", "results": [{"status": "passed"}]}]}
                    for title in sorted(PLAYWRIGHT_REQUIRED_TITLES)
                ],
            }
        ],
    }


def _load_json(path: Path, failures: list[str]) -> dict[str, Any]:
    if not path.is_file():
        failures.append(f"missing file: {_relative(path)}")
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        failures.append(f"invalid JSON in {_relative(path)}: {exc}")
        return {}


def _check_no_secrets(path: Path, failures: list[str]) -> None:
    text = path.read_text(encoding="utf-8-sig", errors="ignore")
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            failures.append(f"{_relative(path)} contains secret-like material")
            return


def _check_fresh(value: Any, max_age_hours: float, failures: list[str], *, required: bool = True) -> None:
    if max_age_hours <= 0:
        return
    if not value:
        if required:
            failures.append("artifact timestamp is missing")
        return
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        failures.append(f"artifact timestamp is invalid: {value!r}")
        return
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)
    if age > timedelta(hours=max_age_hours):
        failures.append(f"artifact is stale: {round(age.total_seconds() / 3600, 1)} hours old")


def _check_web_proof_manifest(screenshot_dir: Path, max_age_hours: float, failures: list[str]) -> None:
    manifest_path = screenshot_dir / PLAYWRIGHT_PROOF_MANIFEST
    manifest = _load_json(manifest_path, failures)
    if not manifest:
        return
    _check_no_secrets(manifest_path, failures)
    if manifest.get("app") != "Thought Pins":
        failures.append("web proof manifest app must be Thought Pins")
    _check_fresh(manifest.get("generated_at_utc"), max_age_hours, failures)

    raw_screenshots = manifest.get("screenshots")
    if not isinstance(raw_screenshots, list):
        failures.append("web proof manifest screenshots must be a list")
        return

    screenshots: dict[str, dict[str, Any]] = {}
    for raw in raw_screenshots:
        if not isinstance(raw, dict):
            failures.append("web proof manifest contains a non-object screenshot entry")
            continue
        filename = str(raw.get("file") or "")
        if not filename or "/" in filename or "\\" in filename:
            failures.append(f"web proof manifest contains invalid screenshot file name: {filename!r}")
            continue
        if filename in screenshots:
            failures.append(f"web proof manifest has duplicate screenshot entry: {filename}")
            continue
        screenshots[filename] = raw

    extras = sorted(set(screenshots) - set(PLAYWRIGHT_REQUIRED_SCREENSHOTS))
    if extras:
        failures.append(f"web proof manifest has unexpected screenshot entries: {extras}")

    for filename, minimum in sorted(PLAYWRIGHT_REQUIRED_SCREENSHOTS.items()):
        entry = screenshots.get(filename)
        if not entry:
            failures.append(f"web proof manifest missing screenshot entry: {filename}")
            continue
        expected_scenario = PLAYWRIGHT_REQUIRED_SCREENSHOT_SCENARIOS[filename]
        if entry.get("scenario") != expected_scenario:
            failures.append(
                f"web proof manifest scenario mismatch for {filename}: "
                f"expected {expected_scenario!r}, got {entry.get('scenario')!r}"
            )
        min_width, min_height = minimum
        if _safe_int(entry.get("min_width")) < min_width or _safe_int(entry.get("min_height")) < min_height:
            failures.append(
                f"web proof manifest minimum dimensions too small for {filename}: "
                f"{entry.get('min_width')}x{entry.get('min_height')}, expected at least {min_width}x{min_height}"
            )
        viewport = str(entry.get("viewport") or "")
        if not viewport:
            failures.append(f"web proof manifest missing viewport for {filename}")


def _check_screenshots(screenshot_dir: Path, failures: list[str]) -> None:
    if not screenshot_dir.is_dir():
        failures.append(f"web smoke screenshot directory missing: {_relative(screenshot_dir)}")
        return
    for name, minimum in sorted(PLAYWRIGHT_REQUIRED_SCREENSHOTS.items()):
        path = screenshot_dir / name
        if not path.is_file() or path.stat().st_size <= 32:
            failures.append(f"web smoke screenshot missing or empty: {_relative(path)}")
            continue
        inspection = _png_inspection(path)
        if inspection is None:
            failures.append(f"web smoke screenshot is not a valid PNG: {_relative(path)}")
            continue
        min_width, min_height = minimum
        if inspection.width < min_width or inspection.height < min_height:
            failures.append(
                f"web smoke screenshot too small: {_relative(path)} is {inspection.width}x{inspection.height}, "
                f"expected at least {min_width}x{min_height}"
            )
            continue
        if not _has_visible_content(inspection):
            failures.append(
                f"web smoke screenshot appears blank or low-detail: {_relative(path)} "
                f"has {inspection.distinct_samples} sampled color(s), luma range {inspection.luma_range}"
            )


def _png_inspection(path: Path) -> PngInspection | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) < 33 or data[:8] != PNG_SIGNATURE:
        return None

    width = height = bit_depth = color_type = interlace = -1
    idat_parts: list[bytes] = []
    offset = 8
    while offset + 12 <= len(data):
        length = int.from_bytes(data[offset : offset + 4], "big")
        kind = data[offset + 4 : offset + 8]
        start = offset + 8
        stop = start + length
        if stop + 4 > len(data):
            return None
        payload = data[start:stop]
        if kind == b"IHDR":
            if length != 13:
                return None
            width, height, bit_depth, color_type, _compression, _filter, interlace = struct.unpack(">IIBBBBB", payload)
        elif kind == b"IDAT":
            idat_parts.append(payload)
        elif kind == b"IEND":
            break
        offset = stop + 4

    if width <= 0 or height <= 0 or bit_depth != 8 or interlace != 0 or not idat_parts:
        return None
    bpp = _png_bytes_per_pixel(color_type)
    if bpp is None:
        return None

    stride = width * bpp
    expected = (stride + 1) * height
    try:
        raw = zlib.decompress(b"".join(idat_parts))
    except zlib.error:
        return None
    if len(raw) < expected:
        return None

    previous = bytearray(stride)
    luma_min = 255
    luma_max = 0
    samples: set[tuple[int, ...]] = set()
    row_step = max(1, height // 512)
    pixel_step = max(1, width // 256)
    position = 0
    for row_index in range(height):
        filter_type = raw[position]
        position += 1
        row = bytearray(raw[position : position + stride])
        position += stride
        if not _png_unfilter(row, previous, filter_type, bpp):
            return None
        if row_index % row_step == 0:
            for x in range(0, width, pixel_step):
                color, luma = _sample_png_pixel(row, x * bpp, color_type)
                samples.add(color)
                luma_min = min(luma_min, luma)
                luma_max = max(luma_max, luma)
                if len(samples) > 512 and luma_max - luma_min >= 64:
                    break
        previous = row
    return PngInspection(
        width=width, height=height, luma_min=luma_min, luma_max=luma_max, distinct_samples=len(samples)
    )


def _png_bytes_per_pixel(color_type: int) -> int | None:
    return {
        0: 1,  # grayscale
        2: 3,  # RGB
        3: 1,  # indexed color
        4: 2,  # grayscale + alpha
        6: 4,  # RGBA
    }.get(color_type)


def _png_unfilter(row: bytearray, previous: bytearray, filter_type: int, bpp: int) -> bool:
    if filter_type == 0:
        return True
    if filter_type == 1:
        for index in range(bpp, len(row)):
            row[index] = (row[index] + row[index - bpp]) & 0xFF
        return True
    if filter_type == 2:
        for index, up in enumerate(previous):
            row[index] = (row[index] + up) & 0xFF
        return True
    if filter_type == 3:
        for index in range(len(row)):
            left = row[index - bpp] if index >= bpp else 0
            up = previous[index]
            row[index] = (row[index] + ((left + up) // 2)) & 0xFF
        return True
    if filter_type == 4:
        for index in range(len(row)):
            left = row[index - bpp] if index >= bpp else 0
            up = previous[index]
            upper_left = previous[index - bpp] if index >= bpp else 0
            row[index] = (row[index] + _paeth(left, up, upper_left)) & 0xFF
        return True
    return False


def _paeth(left: int, up: int, upper_left: int) -> int:
    estimate = left + up - upper_left
    left_distance = abs(estimate - left)
    up_distance = abs(estimate - up)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= up_distance and left_distance <= upper_left_distance:
        return left
    if up_distance <= upper_left_distance:
        return up
    return upper_left


def _sample_png_pixel(row: bytearray, offset: int, color_type: int) -> tuple[tuple[int, ...], int]:
    if color_type == 0:
        value = row[offset]
        return (value,), value
    if color_type == 2:
        red, green, blue = row[offset], row[offset + 1], row[offset + 2]
        return (red, green, blue), _luma(red, green, blue)
    if color_type == 3:
        value = row[offset]
        return (value,), value
    if color_type == 4:
        gray, alpha = row[offset], row[offset + 1]
        return (gray, alpha), gray if alpha else 255
    red, green, blue, alpha = row[offset], row[offset + 1], row[offset + 2], row[offset + 3]
    return (red, green, blue, alpha), _luma(red, green, blue) if alpha else 255


def _luma(red: int, green: int, blue: int) -> int:
    return (red * 299 + green * 587 + blue * 114) // 1000


def _has_visible_content(inspection: PngInspection) -> bool:
    return (inspection.distinct_samples >= 2 and inspection.luma_range >= 32) or (
        inspection.distinct_samples >= 8 and inspection.luma_range >= 8
    )


def _png_dimensions(path: Path) -> tuple[int, int] | None:
    inspection = _png_inspection(path)
    if inspection is None:
        return None
    return inspection.width, inspection.height


def _minimal_png(width: int, height: int) -> bytes:
    return _pattern_png(width, height)


def _solid_png(width: int, height: int, red: int = 255, green: int = 255, blue: int = 255) -> bytes:
    rows = []
    pixel = bytes([red & 0xFF, green & 0xFF, blue & 0xFF])
    for _row in range(height):
        rows.append(b"\x00" + (pixel * width))
    return _png_from_scanlines(width, height, b"".join(rows))


def _pattern_png(width: int, height: int) -> bytes:
    rows: list[bytes] = []
    width_divisor = max(width - 1, 1)
    height_divisor = max(height - 1, 1)
    for y in range(height):
        row = bytearray(b"\x00")
        for x in range(width):
            red = (x * 255) // width_divisor
            green = (y * 255) // height_divisor
            blue = 72 if ((x // 32) + (y // 32)) % 2 else 224
            row.extend((red, green, blue))
        rows.append(bytes(row))
    return _png_from_scanlines(width, height, b"".join(rows))


def _png_from_scanlines(width: int, height: int, scanlines: bytes) -> bytes:
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr = _png_chunk(b"IHDR", ihdr_data)
    idat = _png_chunk(b"IDAT", zlib.compress(scanlines))
    iend = _png_chunk(b"IEND", b"")
    return PNG_SIGNATURE + ihdr + idat + iend


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    checksum = zlib.crc32(kind + payload) & 0xFFFFFFFF
    return len(payload).to_bytes(4, "big") + kind + payload + checksum.to_bytes(4, "big")


def _collect_values(value: Any, key: str) -> set[Any]:
    found: set[Any] = set()
    if isinstance(value, dict):
        for item_key, item_value in value.items():
            if item_key == key:
                found.add(item_value)
            found.update(_collect_values(item_value, key))
    elif isinstance(value, list):
        for item in value:
            found.update(_collect_values(item, key))
    return found


def _latest(pattern: str) -> Path | None:
    matches = sorted(REPORTS.glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def _resolve_path(value: str) -> Path | None:
    if not value:
        return None
    return Path(value)


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except Exception:
        return str(path)


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _finish(report: ProofReport, *, print_json: bool, write_report: bool = True) -> int:
    report.status = "passed" if all(result.status == "passed" for result in report.results) else "failed"
    if write_report:
        REPORTS.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = REPORTS / f"external-proof-artifacts-{stamp}.json"
        report.report_path = str(path)
        path.write_text(json.dumps(asdict(report), indent=2, sort_keys=True), encoding="utf-8")
    payload = asdict(report)
    if print_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"External proof artifact validation: {report.status}")
        for result in report.results:
            suffix = f" ({result.reason})" if result.reason else ""
            print(f"- {result.status:7} {result.name}: {result.path or 'none'}{suffix}")
        if report.report_path:
            print(f"Report: {report.report_path}")
    return 0 if report.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
