from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "production_parity_check.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("production_parity_check", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_live_health_sends_configured_api_key(monkeypatch) -> None:
    module = _load_module()
    captured: dict[str, object] = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "status": "ok",
                "checks": {
                    "llm": {"configured": True, "status": "configured"},
                    "vector": {"status": "ok"},
                    "jobs": {"pending": 0, "retry": 0, "running": 0},
                    "worker": {"status": "ok"},
                },
            }

    def fake_get(url: str, **kwargs):
        captured.update(url=url, **kwargs)
        return Response()

    monkeypatch.setattr(module.httpx, "get", fake_get)
    checks = module._check_live_api("https://example.test", strict=True, api_key="rehearsal-key")

    assert captured["headers"] == {"X-API-Key": "rehearsal-key"}
    assert captured["url"] == "https://example.test/v1/health/deep"
    assert all(check.status == "passed" for check in checks)


def test_compose_shape_keeps_hosted_transcription_healthy() -> None:
    module = _load_module()

    checks = {check.name: check for check in module._check_compose_shape()}

    for name in (
        "API hosted transcription",
        "API transcription credential fallback",
        "Worker hosted transcription",
        "Worker transcription credential fallback",
        "Worker process healthcheck",
        "Worker broker healthcheck",
    ):
        assert checks[name].status == "passed", checks[name].detail
