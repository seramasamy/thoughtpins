"""A spend cap is only as honest as the price map behind it.

`usage.estimate_cost_usd` meters an unpriced runtime at `LLM_DEFAULT_*`. That is
a guess, and guessing low is the dangerous direction: the cap in
`ensure_budget_available` is derived from the same number, so real spend runs
past the limit by whatever multiple the guess was wrong by. Metering a $3/$15
model against the $0.30/$1.20 default overshoots a cap roughly tenfold — the
budget reports headroom while the deposit drains.

So production refuses to start with an unpriced runtime, rather than warning
into a log nobody reads while the bill runs.
"""

from __future__ import annotations

import pytest

from thoughtpins import usage


@pytest.fixture(autouse=True)
def _reset_price_cache():
    """The map is process-cached, so every test must start from a clean read."""
    usage._price_map = None
    usage._unpriced_warned.clear()
    yield
    usage._price_map = None
    usage._unpriced_warned.clear()


def _set_pricing(monkeypatch, payload: str) -> None:
    from thoughtpins.config import config

    monkeypatch.setattr(config, "LLM_PRICING_JSON", payload)
    monkeypatch.setattr(type(config), "LLM_PRICING_JSON", payload)
    usage._price_map = None


def test_a_priced_model_meters_at_its_configured_rate(monkeypatch):
    _set_pricing(monkeypatch, '{"frontier-open":{"input_per_1m":3.0,"output_per_1m":15.0}}')

    cost = usage.estimate_cost_usd("frontier-open", prompt_tokens=1_000_000, completion_tokens=1_000_000)

    assert cost == pytest.approx(18.0)
    assert usage.is_priced("frontier-open") is True


def test_an_unpriced_model_is_reported_rather_than_silently_cheap(monkeypatch):
    """The failure this guards against: metering 10x under the real rate."""
    _set_pricing(monkeypatch, "{}")

    assert usage.is_priced("frontier-open") is False
    metered = usage.estimate_cost_usd("frontier-open", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    real = 3.0 + 15.0

    assert metered < real / 10, "the default rate is far below a frontier model, which is the whole risk"


def test_the_unpriced_warning_fires_once_per_model(monkeypatch):
    _set_pricing(monkeypatch, "{}")
    seen: list[str] = []
    monkeypatch.setattr(usage.logger, "warning", lambda message, *a, **k: seen.append(str(message)))

    for _ in range(5):
        usage.estimate_cost_usd("frontier-open", prompt_tokens=10, completion_tokens=10)
    usage.estimate_cost_usd("another-model", prompt_tokens=10, completion_tokens=10)

    assert len(seen) == 2, "one warning per distinct model, not one per call"


def test_production_refuses_an_unpriced_configured_runtime(monkeypatch):
    from thoughtpins.config_validation import llm_pricing_problems

    _set_pricing(monkeypatch, "{}")

    problems = llm_pricing_problems(("frontier-open", "", ""))

    assert problems, "an unpriced chat runtime must block production startup"
    assert "LLM_PRICING_JSON" in problems[0]


def test_production_accepts_a_fully_priced_configuration(monkeypatch):
    from thoughtpins.config_validation import llm_pricing_problems

    _set_pricing(
        monkeypatch,
        '{"chat-a":{"input_per_1m":3.0,"output_per_1m":15.0},"extract-b":{"input_per_1m":0.3,"output_per_1m":1.2}}',
    )
    assert llm_pricing_problems(("chat-a", "chat-a", "extract-b")) == []


def test_the_guard_is_reachable_from_real_startup_validation(monkeypatch):
    """Calling the helper directly proves nothing if startup never calls it.

    Written after the first version of these tests passed with the check
    unwired from validate_startup: every assertion exercised the helper in
    isolation, so deleting the one line that invoked it changed nothing.
    """
    from thoughtpins.config import config

    _set_pricing(monkeypatch, "{}")
    for attr, value in (
        ("ENVIRONMENT", "production"),
        ("LLM_MODEL", "frontier-open"),
        ("LLM_FALLBACK_MODEL", ""),
        ("LLM_EXTRACTION_MODEL", ""),
        ("LLM_API_KEY", "set-so-a-different-problem-does-not-mask-this"),
    ):
        monkeypatch.setattr(config, attr, value)
        monkeypatch.setattr(type(config), attr, value)

    problems = config.validate_startup()

    assert any("LLM_PRICING_JSON" in problem for problem in problems), (
        "startup validation did not surface the unpriced runtime; the guard exists but is not wired in"
    )


def test_the_check_uses_the_name_the_client_actually_requests(monkeypatch):
    """Pricing a display label does not price the model the request sends.

    `normalize_llm_model_name` strips a "[variant]" suffix before the call, so
    a price map keyed on the label would validate cleanly and still meter at
    the default rate — the exact failure this guard exists to prevent.
    """
    from thoughtpins.config_validation import llm_pricing_problems

    _set_pricing(monkeypatch, '{"chat-a[large]":{"input_per_1m":3.0,"output_per_1m":15.0}}')
    assert llm_pricing_problems(("chat-a[large]", "", "")), (
        "the label was priced but the request sends 'chat-a', which is unpriced"
    )


def test_every_configured_runtime_is_checked_not_just_the_chat_one(monkeypatch):
    """Extraction runs on every ingested entry, so an unpriced one matters too."""
    from thoughtpins.config_validation import llm_pricing_problems

    _set_pricing(monkeypatch, '{"chat-a":{"input_per_1m":3.0,"output_per_1m":15.0}}')
    assert llm_pricing_problems(("chat-a", "chat-a", "extract-unpriced")), (
        "an unpriced extraction runtime must also block startup"
    )
