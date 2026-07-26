from __future__ import annotations

import importlib.util
import subprocess
import sys
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


def test_web_review_harness_check_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_web_review_harness.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Web review harness check passed." in result.stdout


def test_web_review_harness_rejects_drifted_screenshot_filename() -> None:
    harness = _load_script("check_web_review_harness")
    failures: list[str] = []
    proof = harness._load_external_proof_spec(failures)
    assert proof is not None
    text = (ROOT / "frontend" / "e2e" / "web-review.spec.ts").read_text(encoding="utf-8-sig")
    text = text.replace('file: "auth-review.png"', 'file: "auth-review-drift.png"')

    harness._check_review_proof_contract(text, proof, failures, source_label="synthetic-web-review.spec.ts")

    assert any("auth-review.png" in failure for failure in failures)


def test_web_review_harness_rejects_drifted_screenshot_scenario() -> None:
    harness = _load_script("check_web_review_harness")
    failures: list[str] = []
    proof = harness._load_external_proof_spec(failures)
    assert proof is not None
    text = (ROOT / "frontend" / "e2e" / "web-review.spec.ts").read_text(encoding="utf-8-sig")
    text = text.replace(
        'scenario: "memory card provenance and Obsidian vault paths"',
        'scenario: "memory details"',
    )

    harness._check_review_proof_contract(text, proof, failures, source_label="synthetic-web-review.spec.ts")

    assert any("memory-card-review.png" in failure and "scenario" in failure for failure in failures)
