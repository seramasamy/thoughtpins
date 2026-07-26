from __future__ import annotations


def test_production_rate_limit_does_not_fall_back_to_process_memory(monkeypatch) -> None:
    import pytest

    import thoughtpins.rate_limit as rate_limit
    from thoughtpins.config import config

    for target in (config, type(config)):
        monkeypatch.setattr(target, "ENVIRONMENT", "production")
        monkeypatch.setattr(target, "RATE_LIMIT_ENABLED", True)
        monkeypatch.setattr(target, "REDIS_URL", "")
    monkeypatch.setattr(rate_limit, "_redis_client", None)
    monkeypatch.setattr(rate_limit, "_redis_retry_after", 0.0)

    with pytest.raises(rate_limit.RateLimitBackendUnavailable):
        rate_limit.check_rate_limit("auth:test", limit=5)

    assert rate_limit._memory_hits["auth:test"] == []
