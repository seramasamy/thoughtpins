"""Public pages must answer a signed-out request, slash or no slash.

These are the URLs in PRIVACY_POLICY_URL, TERMS_URL, SUPPORT_URL and
ACCOUNT_DELETION_URL: the ones an app-store reviewer opens, a crawler follows,
and a person pastes with a stray trailing slash. Anything not explicitly
registered falls through to the authenticated API and answers 401, so a legal
page would refuse to load for exactly the people it exists for.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from thoughtpins.api_routes.public import create_public_router

# Every path the product publishes as a public destination.
PUBLIC_PATHS = [
    "/",
    "/privacy",
    "/terms",
    "/support",
    "/security",
    "/ai-disclosure",
    "/account/delete",
    "/delete-account",
    "/classic",
]


@pytest.fixture(scope="module")
def client() -> TestClient:
    app = FastAPI()
    app.include_router(create_public_router())
    # follow_redirects=False so a 307 is visible rather than silently followed.
    return TestClient(app, follow_redirects=False)


@pytest.mark.parametrize("path", PUBLIC_PATHS)
def test_public_page_is_reachable(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 200, path


@pytest.mark.parametrize("path", [p for p in PUBLIC_PATHS if p != "/"])
def test_public_page_is_reachable_with_a_trailing_slash(client: TestClient, path: str) -> None:
    """A stray slash must not turn a legal page into a 401."""
    response = client.get(f"{path}/")
    assert response.status_code == 200, f"{path}/ returned {response.status_code}"


def test_pages_are_html_not_an_api_envelope(client: TestClient) -> None:
    for path in ("/privacy", "/account/delete/"):
        response = client.get(path)
        assert "text/html" in response.headers.get("content-type", ""), path


# ------------------------------------------------------------------- the gate
#
# Registering the route is only half of it. The auth middleware decides before
# routing whether a request needs credentials, and it matched the path string
# exactly — so a registered /privacy/ still answered 401. These assert the gate,
# not the router.


@pytest.mark.parametrize("path", [p for p in PUBLIC_PATHS if p != "/"])
def test_the_auth_gate_treats_both_url_forms_as_public(path: str) -> None:
    from thoughtpins.api_route_policy import is_public_path

    assert is_public_path(path), path
    assert is_public_path(f"{path}/"), f"{path}/"


@pytest.mark.parametrize("path", [p for p in PUBLIC_PATHS if p != "/"])
def test_both_url_forms_survive_maintenance(path: str) -> None:
    """A policy page must stay readable while the service is down."""
    from thoughtpins.api_route_policy import is_maintenance_allowed_path

    assert is_maintenance_allowed_path(f"{path}/"), f"{path}/"


@pytest.mark.parametrize(
    "path",
    ["/v1/entries", "/v1/chat", "/v1/entries/", "/v1/admin/usage", "/v1/library", "/v1/graph/"],
)
def test_normalising_the_slash_did_not_open_anything_else(path: str) -> None:
    """The point of the allowlist is that everything absent from it is closed."""
    from thoughtpins.api_route_policy import is_public_path

    assert not is_public_path(path), path


@pytest.mark.parametrize("path", [*PUBLIC_PATHS, "/robots.txt", "/sitemap.xml"])
def test_public_pages_answer_head_requests(client: TestClient, path: str) -> None:
    """HEAD parity with GET, because that is what non-browsers send.

    FastAPI's `router.get` registers GET alone — it does not add HEAD the way a
    bare Starlette route does — so uptime monitors, `curl -I`, and link checkers
    got 405 from the marketing site's front door while every browser saw 200.
    `/health` had carried an explicit HEAD registration for exactly this reason;
    this pins the same guarantee across every published page.
    """
    response = client.head(path)
    assert response.status_code == 200, f"HEAD {path} answered {response.status_code}"
