from __future__ import annotations

import httpx


def test_extract_doi_accepts_urls_and_trims_sentence_punctuation():
    from thoughtpins_sources.open_access import extract_doi

    assert extract_doi("https://doi.org/10.1038/NATURE12373).") == "10.1038/nature12373"
    assert extract_doi("doi:10.5555/ABC.DEF") == "10.5555/abc.def"
    assert extract_doi("https://example.com/no-identifier") is None


def test_open_access_resolver_prefers_repository_location():
    from thoughtpins_sources.open_access import resolve_open_access

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["email"] == "support@thoughtpins.com"
        return httpx.Response(
            200,
            json={
                "is_oa": True,
                "best_oa_location": {
                    "url_for_landing_page": "https://publisher.example/open-copy",
                    "host_type": "publisher",
                    "license": "cc-by",
                    "version": "publishedVersion",
                },
                "oa_locations": [
                    {
                        "url_for_landing_page": "https://repository.example/items/123",
                        "url_for_pdf": "https://repository.example/items/123.pdf",
                        "host_type": "repository",
                        "license": "cc-by-nc",
                        "version": "acceptedVersion",
                    }
                ],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        candidate = resolve_open_access(
            "https://doi.org/10.1038/nature12373",
            contact_email="support@thoughtpins.com",
            client=client,
        )

    assert candidate is not None
    assert candidate.url == "https://repository.example/items/123"
    assert candidate.rights_basis == "open_license"
    assert candidate.host_type == "repository"


def test_open_access_resolver_returns_none_for_closed_record():
    from thoughtpins_sources.open_access import resolve_open_access

    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"is_oa": False}))
    with httpx.Client(transport=transport) as client:
        candidate = resolve_open_access(
            "10.1038/nature12373",
            contact_email="support@thoughtpins.com",
            client=client,
        )
    assert candidate is None


def test_restricted_doi_uses_authorized_open_copy(monkeypatch):
    from thoughtpins import article_fetch
    from thoughtpins.article_fetch import FetchedSource, fetch_url_text
    from thoughtpins.config import config
    from thoughtpins_sources.open_access import OpenAccessCandidate

    monkeypatch.setattr(config, "ARTICLE_FETCH_PROVIDERS", ["local"])
    monkeypatch.setattr(type(config), "ARTICLE_FETCH_PROVIDERS", ["local"])
    monkeypatch.setattr(config, "ARTICLE_RESTRICTED_DOMAINS", ["publisher.example"])
    monkeypatch.setattr(type(config), "ARTICLE_RESTRICTED_DOMAINS", ["publisher.example"])
    candidate = OpenAccessCandidate(
        doi="10.5555/example",
        url="https://repository.example/record/1",
        landing_url="https://repository.example/record/1",
        pdf_url=None,
        license="cc-by",
        host_type="repository",
        version="acceptedversion",
        rights_basis="open_license",
    )
    monkeypatch.setattr(article_fetch, "_resolve_open_access_candidate", lambda url: candidate)

    def public_fetch(url: str) -> FetchedSource:
        assert url == candidate.url
        return FetchedSource(
            original_url=url,
            url=url,
            title="Authorized Copy",
            text="A complete authorized research article with enough public text for memory extraction. " * 20,
            status="processed",
            source_domain="repository.example",
            access_method="public_fetch",
            rights_basis="public_web",
            fetch_status="fetched",
            canonical_url=url,
            retrieval_quality_score=0.9,
        )

    monkeypatch.setattr(article_fetch, "_fetch_with_local_http", public_fetch)
    fetched = fetch_url_text("https://publisher.example/article/10.5555/example")

    assert fetched.status == "processed"
    assert fetched.original_url == "https://publisher.example/article/10.5555/example"
    assert fetched.url == candidate.url
    assert fetched.rights_basis == "open_license"
    assert fetched.metadata["open_access_resolution"]["doi"] == "10.5555/example"
