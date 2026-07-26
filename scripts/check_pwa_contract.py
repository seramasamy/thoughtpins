"""Validate the installable web shell and its privacy boundary."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def main() -> int:
    failures = check_pwa_contract()
    if failures:
        print("PWA contract check failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("PWA contract check passed: installable shell, encrypted drafts, static-only cache.")
    return 0


def check_pwa_contract() -> list[str]:
    failures: list[str] = []
    manifest_path = FRONTEND / "public" / "manifest.webmanifest"
    worker_path = FRONTEND / "public" / "sw.js"
    main_path = FRONTEND / "src" / "main.tsx"
    capture_path = FRONTEND / "src" / "features" / "capture" / "CaptureView.tsx"

    for path in (manifest_path, worker_path, main_path, capture_path):
        if not path.exists():
            failures.append(f"missing {path.relative_to(ROOT)}")
    if failures:
        return failures

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {
        "name": "Thought Pins",
        "start_url": "/app/",
        "scope": "/app/",
        "display": "standalone",
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            failures.append(f"manifest {key!r} must be {value!r}")
    if not manifest.get("icons"):
        failures.append("manifest must declare an install icon")

    worker = worker_path.read_text(encoding="utf-8")
    if 'const APP_ROOT = "/app/"' not in worker:
        failures.append("service worker scope boundary is missing")
    if 'request.method !== "GET"' not in worker:
        failures.append("service worker must reject mutation caching")
    shell_block = worker.split("const SHELL_ASSETS =", 1)[-1].split("];", 1)[0]
    if any(fragment in shell_block for fragment in ("/v1", "/api", "/health")):
        failures.append("service worker shell list includes a runtime API path")

    main_source = main_path.read_text(encoding="utf-8")
    if "registerAppShellServiceWorker" not in main_source:
        failures.append("production client does not register the app-shell worker")
    capture_source = capture_path.read_text(encoding="utf-8")
    if "new EncryptedDraftQueue" not in capture_source:
        failures.append("capture UI is not using the encrypted offline queue")
    if "draft.id" not in capture_source:
        failures.append("offline replay does not preserve a stable idempotency key")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
