from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _load_script(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_external_proof_self_test_command_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_external_proof_artifacts.py", "--self-test"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "External proof artifact validation: passed" in result.stdout


def test_external_proof_accepts_valid_compose_and_playwright_artifacts(tmp_path: Path) -> None:
    mod = _load_script("check_external_proof_artifacts")
    compose = tmp_path / "compose-rehearsal-test.json"
    playwright = tmp_path / "playwright-web-smoke.json"
    screenshots = tmp_path / "web-smoke"
    screenshots.mkdir()
    _write_compose(compose, mod)
    _write_playwright(playwright, mod)
    _write_screenshots(screenshots, mod)

    compose_result = mod.validate_compose_report(compose, max_age_hours=24)
    playwright_result = mod.validate_playwright_report(playwright, screenshots, max_age_hours=24)

    assert compose_result.status == "passed", compose_result.reason
    assert playwright_result.status == "passed", playwright_result.reason


def test_external_proof_rejects_failed_compose_step(tmp_path: Path) -> None:
    mod = _load_script("check_external_proof_artifacts")
    compose = tmp_path / "compose-rehearsal-test.json"
    _write_compose(compose, mod, failed_step="production parity with live API and RLS")

    result = mod.validate_compose_report(compose, max_age_hours=24)

    assert result.status == "failed"
    assert "production parity with live API and RLS" in result.reason


def test_external_proof_rejects_playwright_without_review_screenshots(tmp_path: Path) -> None:
    mod = _load_script("check_external_proof_artifacts")
    playwright = tmp_path / "playwright-web-smoke.json"
    screenshots = tmp_path / "web-smoke"
    screenshots.mkdir()
    _write_playwright(playwright, mod)

    result = mod.validate_playwright_report(playwright, screenshots, max_age_hours=24)

    assert result.status == "failed"
    assert "desktop-review-shell.png" in result.reason
    assert "mobile-review-shell.png" in result.reason


def test_external_proof_rejects_missing_web_proof_manifest(tmp_path: Path) -> None:
    mod = _load_script("check_external_proof_artifacts")
    playwright = tmp_path / "playwright-web-smoke.json"
    screenshots = tmp_path / "web-smoke"
    screenshots.mkdir()
    _write_playwright(playwright, mod)
    _write_screenshots(screenshots, mod, write_manifest=False)

    result = mod.validate_playwright_report(playwright, screenshots, max_age_hours=24)

    assert result.status == "failed"
    assert "web-proof-manifest.json" in result.reason


def test_external_proof_rejects_mismatched_web_proof_manifest(tmp_path: Path) -> None:
    mod = _load_script("check_external_proof_artifacts")
    playwright = tmp_path / "playwright-web-smoke.json"
    screenshots = tmp_path / "web-smoke"
    screenshots.mkdir()
    _write_playwright(playwright, mod)
    _write_screenshots(screenshots, mod)
    manifest = screenshots / mod.PLAYWRIGHT_PROOF_MANIFEST
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["screenshots"][0]["scenario"] = "generic screenshot"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    result = mod.validate_playwright_report(playwright, screenshots, max_age_hours=24)

    assert result.status == "failed"
    assert "scenario mismatch" in result.reason


def test_external_proof_rejects_placeholder_screenshot_files(tmp_path: Path) -> None:
    mod = _load_script("check_external_proof_artifacts")
    playwright = tmp_path / "playwright-web-smoke.json"
    screenshots = tmp_path / "web-smoke"
    screenshots.mkdir()
    _write_playwright(playwright, mod)
    for name in mod.PLAYWRIGHT_REQUIRED_SCREENSHOTS:
        (screenshots / name).write_bytes(b"\x89PNG\r\n\x1a\n" + (b"placeholder" * 8))

    result = mod.validate_playwright_report(playwright, screenshots, max_age_hours=24)

    assert result.status == "failed"
    assert "not a valid PNG" in result.reason


def test_external_proof_rejects_too_small_screenshots(tmp_path: Path) -> None:
    mod = _load_script("check_external_proof_artifacts")
    playwright = tmp_path / "playwright-web-smoke.json"
    screenshots = tmp_path / "web-smoke"
    screenshots.mkdir()
    _write_playwright(playwright, mod)
    for name in mod.PLAYWRIGHT_REQUIRED_SCREENSHOTS:
        (screenshots / name).write_bytes(mod._minimal_png(120, 120))

    result = mod.validate_playwright_report(playwright, screenshots, max_age_hours=24)

    assert result.status == "failed"
    assert "too small" in result.reason


def test_external_proof_rejects_blank_screenshots(tmp_path: Path) -> None:
    mod = _load_script("check_external_proof_artifacts")
    playwright = tmp_path / "playwright-web-smoke.json"
    screenshots = tmp_path / "web-smoke"
    screenshots.mkdir()
    _write_playwright(playwright, mod)
    for name, dimensions in mod.PLAYWRIGHT_REQUIRED_SCREENSHOTS.items():
        (screenshots / name).write_bytes(mod._solid_png(*dimensions))

    result = mod.validate_playwright_report(playwright, screenshots, max_age_hours=24)

    assert result.status == "failed"
    assert "appears blank or low-detail" in result.reason


def test_gap_report_external_proof_substitutes_local_host_limitations(tmp_path: Path) -> None:
    gap = _load_script("generate_gap_report")
    evidence = {
        "app": "Thought Pins",
        "generated_at_utc": "2026-07-01T00:00:00+00:00",
        "passed": True,
        "release_evidence_complete": False,
        "steps": [
            {"name": "quick release gate", "status": "passed", "seconds": 0.1, "command": []},
            {"name": "external proof artifacts", "status": "passed", "seconds": 0.1, "command": []},
            {
                "name": "docker daemon availability",
                "status": "blocked",
                "seconds": 0.1,
                "command": [],
                "reason": "docker unavailable",
            },
            {
                "name": "playwright web smoke",
                "status": "blocked",
                "seconds": 0.1,
                "command": [],
                "reason": "spawn eperm",
            },
        ],
    }

    summary = gap.build_gap_summary(evidence, evidence_file=tmp_path / "closed-beta-evidence-20260701T000000Z.json")

    assert summary["readiness"] == "evidence-complete closed-beta candidate"
    assert summary["infrastructure_blockers"] == []
    assert summary["substituted_by_external_proof"] == ["docker daemon availability", "playwright web smoke"]


def _write_compose(path: Path, mod, *, failed_step: str = "") -> None:
    now = datetime.now(timezone.utc).isoformat()
    steps = []
    for name in sorted(mod.COMPOSE_REQUIRED_STEPS):
        steps.append({"name": name, "status": "failed" if name == failed_step else "passed", "seconds": 0.1})
    payload = {
        "app": "Thought Pins",
        "generated_at_utc": now,
        "status": "passed",
        "keep_running": False,
        "stopped_compose_project": True,
        "base_url": "http://127.0.0.1:8420",
        "checks": sorted(mod.COMPOSE_REQUIRED_CHECK_MARKERS),
        "steps": steps,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_playwright(path: Path, mod) -> None:
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "generated_at_utc": now,
        "stats": {"expected": len(mod.PLAYWRIGHT_REQUIRED_TITLES), "unexpected": 0, "skipped": 0},
        "suites": [
            {
                "title": "Thought Pins web review smoke",
                "specs": [
                    {"title": title, "tests": [{"status": "expected", "results": [{"status": "passed"}]}]}
                    for title in sorted(mod.PLAYWRIGHT_REQUIRED_TITLES)
                ],
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_screenshots(path: Path, mod, *, write_manifest: bool = True) -> None:
    screenshots = []
    for name, dimensions in mod.PLAYWRIGHT_REQUIRED_SCREENSHOTS.items():
        min_width, min_height = dimensions
        (path / name).write_bytes(mod._minimal_png(min_width, min_height))
        screenshots.append(
            {
                "file": name,
                "scenario": mod.PLAYWRIGHT_REQUIRED_SCREENSHOT_SCENARIOS[name],
                "viewport": _test_viewport(name),
                "min_width": min_width,
                "min_height": min_height,
            }
        )
    if write_manifest:
        (path / mod.PLAYWRIGHT_PROOF_MANIFEST).write_text(
            json.dumps(
                {
                    "app": "Thought Pins",
                    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                    "screenshots": screenshots,
                }
            ),
            encoding="utf-8",
        )


def _test_viewport(filename: str) -> str:
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
