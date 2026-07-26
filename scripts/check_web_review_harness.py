"""Verify the web review smoke-test harness is wired for closed-beta readiness.

This is intentionally static. The actual browser suite is run with
`cd frontend && npm run smoke:web`, but some Windows sandbox shells block Node
child_process spawning, which prevents Playwright from starting Vite/browser
processes locally. The release gate still verifies that the harness, scripts,
mocked API contract, screenshot generation, responsive checks, axe coverage,
and the external proof contract stay synchronized so CI or a normal workstation
can execute the browser test.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
PROOF_CHECKER = ROOT / "scripts" / "check_external_proof_artifacts.py"


def main() -> int:
    failures: list[str] = []
    package_json = _load_json(FRONTEND / "package.json", failures)
    _check_package(package_json, failures)
    _check_text(
        FRONTEND / "playwright.config.ts",
        failures,
        {
            "Playwright config": "defineConfig",
            "Vite web server": "npm run dev -- --port 5179",
            "app route base URL": "http://127.0.0.1:5179/app",
            "HTML report": "reports/playwright-html",
            "JSON report": "playwright-web-smoke.json",
        },
    )
    _check_text(
        FRONTEND / "e2e" / "mockApi.ts",
        failures,
        {
            "client config mock": "/v1/client-config",
            "chat mock": "/v1/chat",
            "account mock": "/v1/me",
            "library mock": "/v1/library",
            "upload mock": "/v1/uploads",
            "export mock": "/v1/export",
            "maintenance config": "maintenance_mode",
            "library call proof": "getLibraryPostCount",
            "upload call proof": "getUploadPostCount",
            "export call proof": "getExportCount",
            "delete account call proof": "getDeleteAccountCount",
        },
    )
    review_spec_path = FRONTEND / "e2e" / "web-review.spec.ts"
    _check_text(
        review_spec_path,
        failures,
        {
            "axe accessibility scan": "AxeBuilder",
            "desktop viewport": "desktop",
            "tablet viewport": "tablet",
            "mobile viewport": "mobile",
            "proof manifest artifact": "web-proof-manifest.json",
            "proof manifest writer": "captureProofScreenshot",
            "serial proof suite": 'mode: "serial"',
            "overflow guard": "expectNoHorizontalOverflow",
            "founder leakage assertion": "founder",
        },
    )
    proof = _load_external_proof_spec(failures)
    review_spec = _read_text(review_spec_path, failures)
    if proof is not None and review_spec:
        _check_review_proof_contract(
            review_spec, proof, failures, source_label=review_spec_path.relative_to(ROOT).as_posix()
        )

    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        print(f"Web review harness check failed: {len(failures)} failure(s).")
        return 1
    print("Web review harness check passed.")
    return 0


def _load_json(path: Path, failures: list[str]) -> dict:
    text = _read_text(path, failures)
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception as exc:
        failures.append(f"Invalid JSON in {path.relative_to(ROOT)}: {exc}")
        return {}


def _load_external_proof_spec(failures: list[str]) -> ModuleType | None:
    if not PROOF_CHECKER.is_file():
        failures.append(f"Missing external proof checker: {PROOF_CHECKER.relative_to(ROOT)}")
        return None
    spec = importlib.util.spec_from_file_location("thoughtpins_external_proof_contract", PROOF_CHECKER)
    if spec is None or spec.loader is None:
        failures.append(f"Could not import external proof checker: {PROOF_CHECKER.relative_to(ROOT)}")
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        failures.append(f"Could not load external proof checker: {exc}")
        return None
    return module


def _check_package(package_json: dict, failures: list[str]) -> None:
    scripts = package_json.get("scripts") or {}
    dev_deps = package_json.get("devDependencies") or {}
    expected_scripts = {
        "smoke:web": "playwright test",
        "install:playwright": "playwright install chromium",
    }
    for name, command in expected_scripts.items():
        if scripts.get(name) != command:
            failures.append(f"frontend/package.json script {name!r} must be {command!r}")
    for dep in ("@playwright/test", "@axe-core/playwright"):
        if dep not in dev_deps:
            failures.append(f"frontend/package.json missing devDependency {dep}")


def _check_review_proof_contract(text: str, proof: ModuleType, failures: list[str], *, source_label: str) -> None:
    manifest = getattr(proof, "PLAYWRIGHT_PROOF_MANIFEST", "")
    if manifest and manifest not in text:
        failures.append(f"{source_label} missing proof manifest artifact: {manifest}")

    required_titles: set[str] = set(getattr(proof, "PLAYWRIGHT_REQUIRED_TITLES", set()))
    for title in sorted(required_titles):
        if title.startswith("local app shell is responsive and navigable on "):
            viewport = title.removeprefix("local app shell is responsive and navigable on ")
            if viewport in {"desktop", "tablet", "mobile"}:
                if "local app shell is responsive and navigable on ${viewport.viewportName}" not in text:
                    failures.append(f"{source_label} missing responsive shell title template")
                if f'viewportName: "{viewport}"' not in text:
                    failures.append(f"{source_label} missing responsive shell viewport: {viewport}")
            else:
                if "local app shell is responsive and navigable on ${viewport.name}" not in text:
                    failures.append(f"{source_label} missing current-device shell title template")
                if f'name: "{viewport}"' not in text:
                    failures.append(f"{source_label} missing current-device viewport: {viewport}")
            continue
        if title not in text:
            failures.append(f"{source_label} missing required Playwright test title: {title}")

    required_screenshots: dict[str, tuple[int, int]] = dict(getattr(proof, "PLAYWRIGHT_REQUIRED_SCREENSHOTS", {}))
    required_scenarios: dict[str, Any] = dict(getattr(proof, "PLAYWRIGHT_REQUIRED_SCREENSHOT_SCENARIOS", {}))
    for filename, dimensions in sorted(required_screenshots.items()):
        if f'file: "{filename}"' not in text:
            failures.append(f"{source_label} missing required proof screenshot file: {filename}")
        scenario = required_scenarios.get(filename)
        if scenario and f'scenario: "{scenario}"' not in text:
            failures.append(f"{source_label} missing required proof screenshot scenario for {filename}: {scenario}")
        min_width, min_height = dimensions
        if f"min_width: {min_width}" not in text:
            failures.append(f"{source_label} missing minimum width {min_width} for proof screenshot {filename}")
        if f"min_height: {min_height}" not in text:
            failures.append(f"{source_label} missing minimum height {min_height} for proof screenshot {filename}")


def _check_text(path: Path, failures: list[str], markers: dict[str, str]) -> None:
    text = _read_text(path, failures)
    if not text:
        return
    for label, marker in markers.items():
        if marker not in text:
            failures.append(f"{path.relative_to(ROOT)} missing {label}: {marker}")


def _read_text(path: Path, failures: list[str]) -> str:
    if not path.is_file():
        failures.append(f"Missing file: {path.relative_to(ROOT)}")
        return ""
    return path.read_text(encoding="utf-8-sig", errors="ignore")


if __name__ == "__main__":
    raise SystemExit(main())
