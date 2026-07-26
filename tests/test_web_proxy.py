from __future__ import annotations

from fastapi.testclient import TestClient

from thoughtpins import web_proxy


def test_web_proxy_health_and_app_shell() -> None:
    client = TestClient(web_proxy.app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    app = client.get("/app")
    assert app.status_code == 200
    assert "Thought Pins" in app.text


def test_web_proxy_static_paths_stay_inside_frontend(tmp_path) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("Thought Pins", encoding="utf-8")
    outside = tmp_path / "secret.txt"
    outside.write_text("nope", encoding="utf-8")

    assert web_proxy._safe_frontend_file(frontend, "index.html") == frontend.resolve() / "index.html"
    assert web_proxy._safe_frontend_file(frontend, "../secret.txt") is None


def test_web_proxy_does_not_forward_hop_by_hop_headers() -> None:
    headers = web_proxy._forward_headers(
        [
            ("Authorization", "Bearer test"),
            ("Host", "example.test"),
            ("Connection", "keep-alive"),
            ("X-Request-ID", "req-1"),
        ]
    )

    assert headers == {"Authorization": "Bearer test", "X-Request-ID": "req-1"}
