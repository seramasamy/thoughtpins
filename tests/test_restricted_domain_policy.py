"""Publisher access limits apply to anything serving other people.

The personal offline build may retrieve from publishers its operator holds
subscriptions to. The hosted service may not, and must not be able to — not by
configuration, not by an environment variable set in the wrong place, not by
someone copying a .env between machines.

So the separation is enforced twice, and both are tested: the retrieval check
itself ignores the flag on a shared deployment, and startup refuses to boot.
"""

from __future__ import annotations

import pytest

RESTRICTED = "https://www.wsj.com/articles/example"
OPEN = "https://example.com/a-public-post"


@pytest.fixture
def article_config(monkeypatch):
    from thoughtpins.config import Config, config

    def apply(environment: str, allow: bool) -> None:
        for key, value in (("ENVIRONMENT", environment), ("ARTICLE_ALLOW_RESTRICTED_DOMAINS", allow)):
            monkeypatch.setattr(config, key, value)
            monkeypatch.setattr(Config, key, value)

    return apply


def test_hosted_service_refuses_restricted_publishers(article_config):
    from thoughtpins.article_parsing import _is_restricted_fetch_domain

    article_config("production", False)
    assert _is_restricted_fetch_domain(RESTRICTED) is True


def test_hosted_service_still_refuses_even_if_the_flag_is_forced_on(article_config):
    """Configuration must not be able to open this on a shared deployment."""
    from thoughtpins.article_parsing import _is_restricted_fetch_domain

    for environment in ("production", "staging"):
        article_config(environment, True)
        assert _is_restricted_fetch_domain(RESTRICTED) is True, environment


def test_a_shared_deployment_will_not_boot_with_the_flag_on(article_config):
    """The second guard: it never gets as far as serving a request."""
    from thoughtpins.config import config

    article_config("production", True)
    problems = [item for item in config.validate_startup() if "ARTICLE_ALLOW_RESTRICTED_DOMAINS" in item]
    assert problems, "startup must reject this"
    assert "outside local development" in problems[0]


def test_the_personal_offline_build_may_retrieve_them(article_config):
    from thoughtpins.article_parsing import _is_restricted_fetch_domain

    article_config("development", True)
    assert _is_restricted_fetch_domain(RESTRICTED) is False


def test_offline_still_defaults_to_refusing(article_config):
    """Opt in deliberately; running locally is not consent on its own."""
    from thoughtpins.article_parsing import _is_restricted_fetch_domain

    article_config("development", False)
    assert _is_restricted_fetch_domain(RESTRICTED) is True


def test_open_publishers_are_unaffected_either_way(article_config):
    from thoughtpins.article_parsing import _is_restricted_fetch_domain

    for environment, allow in (("production", False), ("development", True)):
        article_config(environment, allow)
        assert _is_restricted_fetch_domain(OPEN) is False


def test_the_flag_is_off_by_default():
    from thoughtpins.config import _env_bool

    assert _env_bool("ARTICLE_ALLOW_RESTRICTED_DOMAINS", False) is False
