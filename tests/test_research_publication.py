import json
from pathlib import Path

import pytest

from thoughtpins.memory.research_replay import assert_close, model_predictions, verify_manifest


def test_publication_detects_altered_artifact_and_path_escape(tmp_path: Path):
    target = tmp_path / "artifact.json"
    target.write_text("{}\n")
    manifest = {"artifacts": {"artifact.json": "0" * 64}, "sources": {}}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_manifest(tmp_path, tmp_path)
    manifest["artifacts"] = {"../outside.json": "0" * 64}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="escapes"):
        verify_manifest(tmp_path, tmp_path)


def test_publication_refuses_missing_metric_or_changed_denominator():
    with pytest.raises(ValueError, match="Schema"):
        assert_close({"hit1": 1}, {"hit1": 1, "queries": 2})
    with pytest.raises(ValueError, match="Numeric"):
        assert_close({"queries": 1}, {"queries": 2})


def test_model_failure_must_preserve_exact_original_order():
    row = {
        "query_id": "synthetic",
        "arm": "model",
        "candidate_ids": ["b", "a"],
        "baseline_ids": ["a", "b"],
        "ranking": ["a", "b"],
        "fallback": "invalid_full_permutation",
        "response": {"kind": "chat", "status": "ok", "finish_reason": "stop", "content": '{"ranking":[0,0]}'},
    }
    assert model_predictions([row])["synthetic", "model"] == ["a", "b"]
    row["ranking"] = ["b", "a"]
    with pytest.raises(ValueError, match="decision mismatch"):
        model_predictions([row])
