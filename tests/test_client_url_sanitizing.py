"""A Windows shell must not be able to put a filesystem path in front of clients.

Git Bash and MSYS rewrite a bare leading-slash argument into a Windows path
before the program sees it, so `WEB_APP_URL=/app` set from that shell is stored
as `C:/Program Files/Git/app`. Production served exactly that value in
`store_urls.web`, where every client reads it to build an update link and the
web app prints it verbatim in its legal screen.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

MANGLED = "C:/Program Files/Git/app"


def test_is_shell_mangled_path_recognises_windows_paths():
    from thoughtpins.config import is_shell_mangled_path

    assert is_shell_mangled_path(MANGLED)
    assert is_shell_mangled_path("D:\\Git\\app")
    assert is_shell_mangled_path("\\\\server\\share")
    # Ordinary values must survive untouched.
    assert not is_shell_mangled_path("/app")
    assert not is_shell_mangled_path("https://thoughtpins.com/app")
    assert not is_shell_mangled_path("")


def test_public_client_url_drops_a_path_and_keeps_a_url():
    from thoughtpins.config import public_client_url

    assert public_client_url(MANGLED) is None
    assert public_client_url("") is None
    assert public_client_url(None) is None
    assert public_client_url("/app") == "/app"
    assert public_client_url("https://thoughtpins.com/app") == "https://thoughtpins.com/app"


def test_client_config_serves_null_rather_than_a_windows_path(isolated_db, monkeypatch):
    from thoughtpins.api import app
    from thoughtpins.config import config

    monkeypatch.setattr(config, "WEB_APP_URL", MANGLED)
    monkeypatch.setattr(config, "IOS_STORE_URL", MANGLED)
    monkeypatch.setattr(config, "ANDROID_STORE_URL", "https://play.google.com/store/apps/details?id=x")

    payload = TestClient(app).get("/v1/client-config").json()

    store_urls = payload["store_urls"]
    assert store_urls["web"] is None, "a filesystem path must never reach a client"
    assert store_urls["ios"] is None
    # A real URL alongside a bad one is still served.
    assert store_urls["android"] == "https://play.google.com/store/apps/details?id=x"


def test_the_deploy_gate_refuses_a_mangled_client_url(monkeypatch):
    import scripts.validate_production as validate_production
    from thoughtpins.config import config

    monkeypatch.setattr(config, "WEB_APP_URL", MANGLED)
    monkeypatch.setattr(config, "IOS_STORE_URL", "")
    monkeypatch.setattr(config, "ANDROID_STORE_URL", "")

    problems = validate_production.client_url_problems()

    assert len(problems) == 1
    assert "WEB_APP_URL" in problems[0]
    assert "MSYS_NO_PATHCONV" in problems[0], "the message must say how to set it correctly"

    monkeypatch.setattr(config, "WEB_APP_URL", "https://thoughtpins.com/app")
    assert validate_production.client_url_problems() == []
