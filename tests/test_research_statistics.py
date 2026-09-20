import math

import pytest

from thoughtpins.memory.research_statistics import holm, paired_analysis, query_metrics


def test_hand_calculated_graded_ndcg_and_complete_support() -> None:
    metrics = query_metrics(["b", "b", "x", "a"], {"a": 2, "b": 1}, exponential=True)
    assert metrics["ndcg10"] == pytest.approx((1 + 3 / 2) / (3 + 1 / math.log2(3)))
    assert metrics["complete5"] == 1
    assert metrics["recall5"] == 1
    assert metrics["hit1"] == 1
    assert query_metrics(["b"], {"a": 1, "b": 1})["recall5"] == 0.5
    with pytest.raises(ValueError):
        query_metrics(["a"], {})


def test_five_topic_randomization_has_coarse_resolution() -> None:
    result = paired_analysis([1] * 10, [0] * 10, [str(i // 2) for i in range(10)])
    assert result["groups"] == 5
    assert result["p_value"] == 2 / 32
    assert result["limited_power"]
    assert result["ci95"] == [1, 1]


def test_holm_step_down_and_zero_paired_difference() -> None:
    assert holm({"a": 0.01, "b": 0.03, "c": 0.2}) == {"a": 0.03, "b": 0.06, "c": 0.2}
    result = paired_analysis([0.2, 0.6], [0.2, 0.6], ["a", "b"])
    assert result["delta"] == 0 and result["p_value"] == 1
    assert result["ci95"] == [0, 0]
