from __future__ import annotations

from pathlib import Path

import pytest

from scripts.route_contracts import RouteDiscoveryError, discover_api_routes

ROOT = Path(__file__).resolve().parents[1]


def test_route_discovery_follows_modular_api_routers() -> None:
    routes = discover_api_routes(ROOT)

    assert ("DELETE", "/v1/me") in routes
    assert ("GET", "/v1/export") in routes
    assert ("POST", "/v1/chat") in routes


def test_route_discovery_fails_closed_without_authored_routes(tmp_path: Path) -> None:
    with pytest.raises(RouteDiscoveryError, match="no API route modules"):
        discover_api_routes(tmp_path)
