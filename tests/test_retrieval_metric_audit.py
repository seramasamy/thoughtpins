"""Hand-worked checks for the independent publication auditor."""

import math
import runpy
from pathlib import Path

import pytest

AUDIT = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/audit_retrieval_metrics.py"))


def test_audit_distinguishes_first_hit_partial_recall_and_complete_support():
    result = AUDIT["measure"](["wrong", "a", "b"], {"a": 1, "b": 1})
    expected = (1 / math.log2(3) + 0.5) / (1 + 1 / math.log2(3))
    assert result["ndcg10"] == pytest.approx(expected)
    assert result["hit1"] == 0
    assert result["mrr"] == 0.5
    assert result["complete5"] == result["recall5"] == 1
    assert AUDIT["measure"](["a"], {"a": 1, "b": 1})["complete5"] == 0


def test_audit_preserves_graded_gain_and_rejects_duplicate_or_empty_gold():
    result = AUDIT["measure"](["low", "high"], {"low": 1, "high": 2}, graded=True)
    assert result["ndcg10"] == pytest.approx((1 + 3 / math.log2(3)) / (3 + 1 / math.log2(3)))
    with pytest.raises(ValueError, match="Duplicate"):
        AUDIT["measure"](["a", "a"], {"a": 1})
    with pytest.raises(ValueError, match="Unanswerable"):
        AUDIT["measure"](["a"], {})


def test_audit_counts_failed_model_decision_in_original_order():
    row = {
        "candidate_ids": ["b", "a"],
        "baseline_ids": ["a", "b"],
        "ranking": ["a", "b"],
        "fallback": "invalid_full_permutation",
        "response": {"kind": "chat", "status": "ok", "finish_reason": "stop", "content": '{"ranking": [0, 0]}'},
    }
    AUDIT["check_model"](row)
    row["ranking"] = ["b", "a"]
    with pytest.raises(ValueError, match="fallback mismatch"):
        AUDIT["check_model"](row)


def test_audit_uses_groups_rather_than_counting_related_queries_independently():
    result = AUDIT["paired"]([1.0, 1.0, 1.0], ["one", "one", "two"])
    assert result == {"delta": 1.0, "ci95": [1.0, 1.0], "p_value": 0.5}
