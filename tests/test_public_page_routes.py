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
