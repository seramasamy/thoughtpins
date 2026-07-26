from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _matrix_module():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    path = SCRIPTS / "generate_store_readiness_matrix.py"
    spec = importlib.util.spec_from_file_location("generate_store_readiness_matrix", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8-sig"))


def _synthetic_evidence() -> dict:
    passed_steps = [
        "quick release gate",
        "review account packet",
        "review notes packet",
        "store submission packet",
        "app store compliance",
        "public export hygiene",
        "production parity",
        "startup shutdown smoke",
        "runtime feature smoke",
        "domain readiness",
    ]
    return {
        "app": "Thought Pins",
        "generated_at_utc": "2026-07-01T00:00:00+00:00",
        "release_evidence_complete": False,
        "steps": [{"name": name, "status": "passed", "seconds": 0.1, "command": []} for name in passed_steps],
    }


def test_store_readiness_matrix_maps_policy_requirements_to_evidence() -> None:
    mod = _matrix_module()
    matrix = mod.build_store_readiness_matrix(
        _synthetic_evidence(),
        _load_json("deploy/store/submission-packet.json"),
        _load_json("deploy/store/store-policy-requirements.json"),
        _load_json("deploy/store/native-review-handoff.json"),
    )

    by_id = {item["id"]: item for item in matrix["requirements"]}

    assert matrix["app"] == "Thought Pins"
    assert matrix["summary"]["total_requirements"] == 14
    assert matrix["summary"]["native_source_shells_ready"] is True
    assert matrix["summary"]["native_store_submission_ready"] is False
    assert by_id["apple_in_app_account_deletion"]["readiness"] == "locally_proven"
    assert by_id["google_in_app_account_deletion"]["readiness"] == "locally_proven"
    assert by_id["apple_live_backend"]["readiness"] == "code_ready_needs_external_setup"
    assert by_id["google_secure_handling_and_no_sale"]["readiness"] != "code_gap_missing_evidence"
    assert by_id["apple_ai_disclosure_and_safety_reporting"]["readiness"] != "code_gap_missing_evidence"
    assert by_id["apple_user_generated_content_safety_controls"]["readiness"] != "code_gap_missing_evidence"
    assert by_id["google_ai_generated_content_safety"]["readiness"] != "code_gap_missing_evidence"
    assert "account_deletion_in_app_and_web" in by_id["google_web_account_deletion"]["native_review_flows"]


def test_store_readiness_matrix_writer_outputs_markdown_and_json() -> None:
    mod = _matrix_module()
    output_dir = ROOT / ".tmp" / f"store-readiness-matrix-test-{uuid.uuid4().hex}"
    output_dir.mkdir(parents=True, exist_ok=False)
    result = mod.write_store_readiness_matrix(None, output_dir=output_dir)

    markdown = Path(result["markdown_path"])
    json_path = Path(result["json_path"])

    assert markdown.is_file()
    assert json_path.is_file()
    assert "Thought Pins Store Readiness Matrix" in markdown.read_text(encoding="utf-8")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["summary"]["total_requirements"] == 14


def test_store_readiness_matrix_check_script_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_store_readiness_matrix.py", "--self-test"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Store readiness matrix check passed." in result.stdout
