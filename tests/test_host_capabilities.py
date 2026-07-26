from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _host_module():
    path = ROOT / "scripts" / "check_host_capabilities.py"
    spec = importlib.util.spec_from_file_location("check_host_capabilities", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_host_capability_classifies_environment_blockers() -> None:
    mod = _host_module()

    assert mod.classify_failure(1, "Error: spawn EPERM") == (
        "blocked",
        "Host blocks child-process/browser spawn.",
    )
    status, reason = mod.classify_failure(1, "Cannot connect to the Docker daemon")
    assert status == "blocked"
    assert "Docker daemon" in reason
    assert mod.classify_failure(127, "command not recognized")[0] == "missing"
    assert mod.classify_failure(1, "Executable doesn't exist at C:/ms-playwright/chromium.exe") == (
        "missing",
        "Playwright browser binary is missing.",
    )
    assert mod.classify_failure(2, "assertion failed") == ("failed", "exit code 2: assertion failed")


def test_host_capability_payload_marks_public_and_native_readiness() -> None:
    mod = _host_module()
    report = mod.HostCapabilityReport()
    report.capabilities.extend(
        [
            mod.Capability("docker_daemon", "Docker daemon", "ready", ["compose_rehearsal"]),
            mod.Capability("docker_compose_config", "Docker Compose config", "ready", ["compose_rehearsal"]),
            mod.Capability("playwright_browser_smoke", "Playwright", "ready", ["web_screenshots"]),
            mod.Capability("swift_toolchain", "Swift", "missing", ["native_ios_submission"]),
            mod.Capability("android_gradle_or_wrapper", "Gradle", "ready", ["native_android_submission"]),
            mod.Capability("java_toolchain", "Java", "ready", ["native_android_submission"]),
        ]
    )
    report.summary = mod._summary(report.capabilities)

    payload = mod.report_payload(report)

    assert payload["public_beta_host_ready"] is True
    assert payload["native_submission_host_ready"] is False
    assert "swift_toolchain" in payload["summary"]["native_submission_missing_or_blocked"]


def test_playwright_capability_uses_real_launch_probe_when_requested(monkeypatch, tmp_path) -> None:
    mod = _host_module()
    frontend = tmp_path / "frontend"
    (frontend / "node_modules" / "@playwright" / "test").mkdir(parents=True)
    calls = []

    def fake_run_capability(capability_id, label, command, **kwargs):
        calls.append({"capability_id": capability_id, "label": label, "command": command, "kwargs": kwargs})
        return mod.Capability(
            capability_id, label, "ready", kwargs["required_for"], command, "ok", kwargs["remediation"]
        )

    monkeypatch.setattr(mod, "FRONTEND", frontend)
    monkeypatch.setattr(mod.shutil, "which", lambda name: name if name == "npm" else None)
    monkeypatch.setattr(mod, "_run_capability", fake_run_capability)

    capability = mod._playwright_capability(with_browser_smoke=True)

    assert capability.status == "ready"
    assert calls[0]["command"] == ["node", "scripts/playwright-launch-probe.mjs"]
    assert calls[0]["kwargs"]["cwd"] == frontend
    assert calls[0]["kwargs"]["timeout"] == 60


def test_host_capability_redacts_secret_like_text() -> None:
    mod = _host_module()
    secret = "API_KEY=super-secret token sk-" + "A" * 32

    redacted = mod._redact(secret)

    assert "super-secret" not in redacted
    assert "sk-" + "A" * 32 not in redacted
    assert "<redacted>" in redacted
