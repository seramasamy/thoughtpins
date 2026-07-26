from __future__ import annotations

import httpx


def _long_article(marker: str = "silver compass") -> str:
    return (
        f"This public article explains the {marker} detail and why source provenance matters. "
        "It has enough readable body text to be treated as a legitimate document source. "
        "The user wants this article remembered as external reading memory, not as a lived journal entry. "
    ) * 12


def test_fetch_url_rejects_private_local_targets(monkeypatch):
    from thoughtpins.config import config
    from thoughtpins.library import fetch_url_text

    monkeypatch.setattr(config, "ARTICLE_ALLOW_PRIVATE_URLS", False)
    monkeypatch.setattr(type(config), "ARTICLE_ALLOW_PRIVATE_URLS", False)

    fetched = fetch_url_text("http://127.0.0.1:8420/private")

    assert fetched.status == "error"
    assert fetched.rights_basis == "metadata_only"
    assert "blocked" in fetched.error.lower()


def test_fetch_url_rejects_embedded_credentials_and_non_web_ports(monkeypatch):
    from thoughtpins.article_fetch import _validate_fetch_url
    from thoughtpins.config import config

    monkeypatch.setattr(config, "ARTICLE_ALLOW_PRIVATE_URLS", False)
    monkeypatch.setattr(type(config), "ARTICLE_ALLOW_PRIVATE_URLS", False)

    assert _validate_fetch_url("https://user:secret@example.com/story")[0] is False
    assert _validate_fetch_url("https://example.com:8443/story")[0] is False


def test_local_fetch_validates_redirect_hops_before_following(monkeypatch):
    from thoughtpins import article_fetch

    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})

    monkeypatch.setattr(article_fetch, "_validate_public_dns", lambda url: (True, ""))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        try:
            article_fetch._read_public_http_url("https://example.com/start", client=client)
        except ValueError as exc:
            assert "private" in str(exc).lower()
        else:
            raise AssertionError("private redirect should be rejected")

    assert requests == ["https://example.com/start"]


def test_local_fetch_caps_downloaded_article_bytes(monkeypatch):
    from thoughtpins import article_fetch
    from thoughtpins.config import config

    monkeypatch.setattr(config, "ARTICLE_MAX_FETCH_BYTES", 64)
    monkeypatch.setattr(type(config), "ARTICLE_MAX_FETCH_BYTES", 64)
    monkeypatch.setattr(article_fetch, "_validate_public_dns", lambda url: (True, ""))
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 4096))

    with httpx.Client(transport=transport) as client:
        payload = article_fetch._read_public_http_url("https://example.com/story", client=client)

    assert len(payload.content) == 64


def test_fetch_url_uses_configured_compliant_fallback(monkeypatch):
    from thoughtpins import library
    from thoughtpins.config import config
    from thoughtpins.library import FetchedSource, fetch_url_text

    monkeypatch.setattr(config, "ARTICLE_FETCH_PROVIDERS", ["local", "jina"])
    monkeypatch.setattr(type(config), "ARTICLE_FETCH_PROVIDERS", ["local", "jina"])

    def fake_local(url: str) -> FetchedSource:
        return FetchedSource(
            original_url=url,
            url=url,
            title="Gated story",
            text="Subscribe to continue.",
            status="needs_text",
            error="Not enough text",
            source_domain="example.com",
            access_method="public_fetch",
            rights_basis="metadata_only",
            fetch_status="fetched",
            canonical_url=url,
            paywall_detected=True,
            retrieval_quality_score=0.05,
        )

    def fake_jina(url: str) -> FetchedSource:
        return FetchedSource(
            original_url=url,
            url=url,
            title="Public reader story",
            text=_long_article("blue lantern"),
            status="processed",
            source_domain="example.com",
            access_method="jina_reader",
            rights_basis="public_web",
            fetch_status="fetched",
            canonical_url=url,
            retrieval_quality_score=0.8,
        )

    monkeypatch.setattr(library, "_fetch_with_local_http", fake_local)
    monkeypatch.setattr(library, "_fetch_with_jina_reader", fake_jina)

    fetched = fetch_url_text("https://example.com/article")

    assert fetched.status == "processed"
    assert fetched.access_method == "jina_reader"
    assert fetched.rights_basis == "public_web"
    assert "blue lantern" in fetched.text
    assert fetched.metadata["fetch_attempts"][0]["provider"] == "local"


def test_fetch_url_uses_paid_specialist_provider_after_cheap_fallbacks(monkeypatch):
    from thoughtpins import library
    from thoughtpins.config import config
    from thoughtpins.library import FetchedSource, fetch_url_text

    monkeypatch.setattr(config, "ARTICLE_FETCH_PROVIDERS", ["local", "jina", "firecrawl", "apify"])
    monkeypatch.setattr(type(config), "ARTICLE_FETCH_PROVIDERS", ["local", "jina", "firecrawl", "apify"])

    def low_quality(provider: str):
        def fake(url: str) -> FetchedSource:
            return FetchedSource(
                original_url=url,
                url=url,
                title=f"{provider} preview",
                text="Subscribe to continue.",
                status="needs_text",
                error="Not enough text",
                source_domain="example.com",
                access_method=provider,
                rights_basis="metadata_only",
                fetch_status="fetched",
                canonical_url=url,
                paywall_detected=True,
                retrieval_quality_score=0.02,
            )

        return fake

    def fake_apify(url: str) -> FetchedSource:
        return FetchedSource(
            original_url=url,
            url=url,
            title="Actor story",
            text=_long_article("amber gear"),
            status="processed",
            source_domain="example.com",
            access_method="apify",
            rights_basis="public_web",
            fetch_status="fetched",
            canonical_url=url,
            retrieval_quality_score=0.9,
        )

    monkeypatch.setattr(library, "_fetch_with_local_http", low_quality("local"))
    monkeypatch.setattr(library, "_fetch_with_jina_reader", low_quality("jina"))
    monkeypatch.setattr(library, "_fetch_with_firecrawl", low_quality("firecrawl"))
    monkeypatch.setattr(library, "_fetch_with_apify", fake_apify)

    fetched = fetch_url_text("https://example.com/article")

    assert fetched.status == "processed"
    assert fetched.access_method == "apify"
    assert "amber gear" in fetched.text
    assert [attempt["provider"] for attempt in fetched.metadata["fetch_attempts"]] == [
        "local",
        "jina",
        "firecrawl",
        "apify",
    ]


def test_known_subscription_publishers_are_metadata_only(monkeypatch):
    from thoughtpins import library
    from thoughtpins.config import config
    from thoughtpins.library import fetch_url_text

    monkeypatch.setattr(config, "ARTICLE_FETCH_PROVIDERS", ["local", "jina", "firecrawl"])
    monkeypatch.setattr(type(config), "ARTICLE_FETCH_PROVIDERS", ["local", "jina", "firecrawl"])
    monkeypatch.setattr(config, "ARTICLE_RESTRICTED_DOMAINS", ["wsj.com", "bloomberg.com"])
    monkeypatch.setattr(type(config), "ARTICLE_RESTRICTED_DOMAINS", ["wsj.com", "bloomberg.com"])

    def should_not_fetch(url: str):
        raise AssertionError("reader providers must not be called for restricted domains")

    monkeypatch.setattr(library, "_fetch_with_local_http", should_not_fetch)
    monkeypatch.setattr(library, "_fetch_with_jina_reader", should_not_fetch)
    monkeypatch.setattr(library, "_fetch_with_firecrawl", should_not_fetch)

    fetched = fetch_url_text("https://www.wsj.com/articles/long-running-ai-agents-are-here-3e3aa89b")

    assert fetched.status == "needs_text"
    assert fetched.rights_basis == "metadata_only"
    assert fetched.fetch_status == "restricted"
    assert fetched.access_method == "metadata_only"
    assert "limits automated access" in fetched.error


def test_paywall_markers_force_metadata_only_even_with_long_text(monkeypatch):
    from thoughtpins.article_fetch import _finalize_fetched_source
    from thoughtpins.config import config

    monkeypatch.setattr(config, "ARTICLE_RESTRICTED_DOMAINS", [])
    monkeypatch.setattr(type(config), "ARTICLE_RESTRICTED_DOMAINS", [])
    long_paywall_text = (
        "This story has a long preview but says subscribe to continue before exposing the rest. "
        "The body is intentionally long enough to exceed the normal article threshold. "
    ) * 20

    fetched = _finalize_fetched_source(
        original_url="https://example.com/paid",
        url="https://example.com/paid",
        title="Paid story",
        text=long_paywall_text,
        source_domain="example.com",
        access_method="jina_reader",
        rights_basis="public_web",
        fetch_status="fetched",
        canonical_url="https://example.com/paid",
    )

    assert fetched.status == "needs_text"
    assert fetched.rights_basis == "metadata_only"
    assert fetched.paywall_detected is True
    assert fetched.text == ""
    assert fetched.metadata["chars"] == 0
    assert fetched.metadata["discarded_unusable_chars"] > 0
    assert "access-gated" in fetched.error


def test_final_canonical_domain_cannot_hide_a_restricted_destination(monkeypatch):
    from thoughtpins.article_fetch import _finalize_fetched_source
    from thoughtpins.config import config

    monkeypatch.setattr(config, "ARTICLE_RESTRICTED_DOMAINS", ["publisher.example"])
    monkeypatch.setattr(type(config), "ARTICLE_RESTRICTED_DOMAINS", ["publisher.example"])

    fetched = _finalize_fetched_source(
        original_url="https://short.example/read/abc",
        url="https://short.example/read/abc",
        title="Redirected story",
        text=_long_article("hidden destination"),
        source_domain="short.example",
        access_method="public_fetch",
        rights_basis="public_web",
        fetch_status="fetched",
        canonical_url="https://publisher.example/story/abc",
    )

    assert fetched.status == "needs_text"
    assert fetched.rights_basis == "metadata_only"
    assert fetched.text == ""


def test_public_substack_subscribe_cta_is_not_mistaken_for_a_gate(monkeypatch):
    from thoughtpins.article_fetch import _finalize_fetched_source
    from thoughtpins.config import config

    monkeypatch.setattr(config, "ARTICLE_RESTRICTED_DOMAINS", [])
    monkeypatch.setattr(type(config), "ARTICLE_RESTRICTED_DOMAINS", [])
    public_post = (
        "This public newsletter essay explains durable memory, source context, and reflective reading. "
        "It contains a complete argument with examples and a clear conclusion for every reader. "
    ) * 24 + " Subscribe now to receive the next public post. Already a subscriber? Sign in."

    fetched = _finalize_fetched_source(
        original_url="https://clear-notes.substack.com/p/public-memory",
        url="https://clear-notes.substack.com/p/public-memory",
        title="Public Memory",
        text=public_post,
        source_domain="clear-notes.substack.com",
        access_method="substack_rss",
        rights_basis="public_feed",
        fetch_status="fetched",
        canonical_url="https://clear-notes.substack.com/p/public-memory?utm_source=share&r=abc",
    )

    assert fetched.status == "processed"
    assert fetched.paywall_detected is False
    assert fetched.rights_basis == "public_feed"
    assert fetched.canonical_url == "https://clear-notes.substack.com/p/public-memory"


def test_substack_public_feed_matches_share_link_and_extracts_metadata():
    from thoughtpins.article_fetch import _parse_substack_feed

    article_html = (
        "<p>This public post explains the amber notebook and how durable ideas connect over time.</p>" * 25
        + "<p>Subscribe now for future posts.</p>"
    )
    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:dc="http://purl.org/dc/elements/1.1/">
      <channel>
        <title>Clear Notes</title>
        <item>
          <title>The Amber Notebook</title>
          <link>https://clear-notes.substack.com/p/the-amber-notebook?utm_source=publication</link>
          <dc:creator>Maya Example</dc:creator>
          <pubDate>Wed, 08 Jul 2026 14:00:00 GMT</pubDate>
          <content:encoded><![CDATA[{article_html}]]></content:encoded>
        </item>
      </channel>
    </rss>"""

    item = _parse_substack_feed(
        feed,
        "https://open.substack.com/pub/clear-notes/p/the-amber-notebook?utm_source=share",
    )

    assert item is not None
    assert item["title"] == "The Amber Notebook"
    assert item["publication"] == "Clear Notes"
    assert item["author"] == "Maya Example"
    assert item["url"] == "https://clear-notes.substack.com/p/the-amber-notebook"
    assert "amber notebook" in item["text"].lower()


def test_apify_provider_is_opt_in(monkeypatch):
    from thoughtpins import library
    from thoughtpins.config import config

    monkeypatch.setattr(config, "APIFY_API_TOKEN", "")
    monkeypatch.setattr(type(config), "APIFY_API_TOKEN", "")
    monkeypatch.setattr(config, "APIFY_READER_ACTOR", "")
    monkeypatch.setattr(type(config), "APIFY_READER_ACTOR", "")

    fetched = library._fetch_with_apify("https://example.com/story")

    assert fetched.status == "needs_text"
    assert fetched.fetch_status == "skipped"
    assert fetched.access_method == "apify"
    assert "APIFY_API_TOKEN" in fetched.error


def test_apify_adapter_normalizes_actor_and_template(monkeypatch):
    from thoughtpins import library
    from thoughtpins.config import config

    monkeypatch.setattr(config, "APIFY_READER_INPUT_TEMPLATE", '{"startUrls":[{"url":"{url}"}],"maxCrawlPages":1}')
    monkeypatch.setattr(
        type(config), "APIFY_READER_INPUT_TEMPLATE", '{"startUrls":[{"url":"{url}"}],"maxCrawlPages":1}'
    )

    assert library._apify_actor_path("apify/website-content-crawler") == "apify~website-content-crawler"
    assert library._apify_input_payload("https://example.com/a") == {
        "startUrls": [{"url": "https://example.com/a"}],
        "maxCrawlPages": 1,
    }
    title, body, metadata = library._extract_apify_item(
        {
            "title": "Clean title",
            "markdown": _long_article("violet theorem"),
            "url": "https://example.com/a",
        },
        "https://example.com/a",
    )
    assert title == "Clean title"
    assert "violet theorem" in body
    assert "item_keys" in metadata


def test_article_fetch_health_shows_cost_tiers_without_secrets(monkeypatch):
    from thoughtpins.config import config
    from thoughtpins.library import article_fetch_health

    monkeypatch.setattr(config, "ARTICLE_FETCH_PROVIDERS", ["local", "jina", "jina", "firecrawl", "apify", "strange"])
    monkeypatch.setattr(
        type(config), "ARTICLE_FETCH_PROVIDERS", ["local", "jina", "jina", "firecrawl", "apify", "strange"]
    )
    monkeypatch.setattr(config, "JINA_API_KEY", "secret-jina")
    monkeypatch.setattr(type(config), "JINA_API_KEY", "secret-jina")
    monkeypatch.setattr(config, "FIRECRAWL_API_KEY", "secret-firecrawl")
    monkeypatch.setattr(type(config), "FIRECRAWL_API_KEY", "secret-firecrawl")
    monkeypatch.setattr(config, "APIFY_API_TOKEN", "secret-apify")
    monkeypatch.setattr(type(config), "APIFY_API_TOKEN", "secret-apify")
    monkeypatch.setattr(config, "APIFY_READER_ACTOR", "apify/website-content-crawler")
    monkeypatch.setattr(type(config), "APIFY_READER_ACTOR", "apify/website-content-crawler")

    health = article_fetch_health()

    assert health["status"] == "warn"
    assert health["providers"] == ["local", "jina", "firecrawl", "apify", "strange"]
    assert health["jina"]["api_key_present"] is True
    assert health["paid_fallbacks_ready"] == ["firecrawl", "apify"]
    assert "secret" not in str(health)
    assert health["unknown_providers"] == ["strange"]


def test_ingest_url_metadata_only_when_text_unavailable(isolated_db, monkeypatch):
    from thoughtpins import library
    from thoughtpins.db import DocumentChunk, DocumentSource, Memory
    from thoughtpins.library import FetchedSource, ingest_url
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram

    monkeypatch.setattr(library, "_index_document_memories", lambda memories: None)

    def fake_fetch(url: str) -> FetchedSource:
        return FetchedSource(
            original_url=url,
            url=url,
            title="Paywalled Example",
            text="Subscribe to continue.",
            status="needs_text",
            error="Fetched page did not expose enough readable article text.",
            source_domain="example.com",
            access_method="public_fetch",
            rights_basis="metadata_only",
            fetch_status="fetched",
            canonical_url=url,
            paywall_detected=True,
            retrieval_quality_score=0.02,
        )

    monkeypatch.setattr(library, "fetch_url_text", fake_fetch)
    session = get_session()
    try:
        user = get_or_create_user_for_telegram("article-metadata-only", session=session)
        result = ingest_url(session, "https://example.com/paywalled", user_id=user.id)

        assert result.status == "needs_text"
        assert result.chunks == 0
        assert result.memories == 2
        assert result.rights_basis == "metadata_only"
        assert result.paywall_detected is True

        doc = session.query(DocumentSource).filter(DocumentSource.id == result.document_id).one()
        assert doc.source_domain == "example.com"
        assert doc.access_method == "public_fetch"
        assert doc.rights_basis == "metadata_only"
        assert doc.paywall_detected is True
        assert doc.retrieval_quality_score == 0.02
        assert "Subscribe to continue" not in doc.raw_text
        assert "Saved link metadata" in doc.raw_text
        assert session.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).count() == 0
        memories = session.query(Memory).filter(Memory.source_provenance == f"document:{doc.id}").all()
        assert any("metadata_only" in memory.text for memory in memories)
        assert any(memory.memory_type == "source_characteristics" for memory in memories)
    finally:
        session.close()


def test_ingest_url_promotes_user_pasted_text_for_paid_source(isolated_db, monkeypatch):
    from thoughtpins import library
    from thoughtpins.db import DocumentChunk, DocumentSource, Memory
    from thoughtpins.library import FetchedSource, ingest_url
    from thoughtpins.store import get_session
    from thoughtpins.users import get_or_create_user_for_telegram

    monkeypatch.setattr(library, "_index_document_memories", lambda memories: None)

    def fake_fetch(url: str) -> FetchedSource:
        return FetchedSource(
            original_url=url,
            url=url,
            title="User Accessible Story",
            text="",
            status="needs_text",
            error="Needs user-provided text",
            source_domain="example.com",
            access_method="public_fetch",
            rights_basis="metadata_only",
            fetch_status="fetched",
            canonical_url=url,
            paywall_detected=True,
        )

    monkeypatch.setattr(library, "fetch_url_text", fake_fetch)
    session = get_session()
    try:
        user = get_or_create_user_for_telegram("article-user-paste", session=session)
        result = ingest_url(
            session,
            "https://example.com/paid",
            user_id=user.id,
            note=_long_article("green obelisk"),
        )

        assert result.status == "processed"
        assert result.access_method == "user_paste"
        assert result.rights_basis == "user_provided"
        assert result.chunks >= 1

        doc = session.query(DocumentSource).filter(DocumentSource.id == result.document_id).one()
        assert "green obelisk" in doc.raw_text
        assert doc.metadata_json["user_note_promoted_to_text"] is True
        reading = doc.metadata_json["reading_analysis"]
        assert reading["publisher"] == "Example"
        assert reading["source_domain"] == "example.com"
        assert "green obelisk" in " ".join(reading["key_concepts"]).lower()
        chunk = session.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).first()
        assert chunk is not None
        assert chunk.token_count and chunk.token_count > 0
        profile = (
            session.query(Memory)
            .filter(
                Memory.source_provenance == f"document:{doc.id}",
                Memory.memory_type == "source_characteristics",
            )
            .one()
        )
        assert "Source: Example" in profile.text
        assert "Key concepts:" in profile.text
    finally:
        session.close()
