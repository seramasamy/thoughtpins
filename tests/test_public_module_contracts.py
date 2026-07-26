"""Small import tests for compatibility surfaces used outside core modules."""


def test_library_keeps_transport_compatibility_aliases() -> None:
    from thoughtpins import article_fetch, library

    assert library.extract_urls is article_fetch.extract_urls
    assert library.article_fetch_health is article_fetch.article_fetch_health
