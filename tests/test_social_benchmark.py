from __future__ import annotations


def test_social_benchmark_is_high_recall_at_test_scale() -> None:
    from thoughtpins.memory.social_benchmark import run_social_benchmark

    result = run_social_benchmark(case_count=320, seed=20260721)

    assert result.settings == 16
    assert result.recall_at_1 >= 0.95
    assert result.recall_at_3 >= 0.995
    assert result.requested_facet_coverage >= 0.98
    assert result.attribution_retention_rate >= 0.995
    assert result.orphan_uncertain_claim_rate == 0.0
    assert result.deterministic_replay is True


def test_public_domain_passage_extraction_preserves_speaker_and_first_person_signal() -> None:
    from thoughtpins.memory.public_domain_eval import CatalogBook, extract_social_passage

    paragraph = (
        'I waited in the long west corridor until Clara said, "The silver compass belongs beside the cedar cabinet." '
        "I wrote the instruction down because Clara had corrected the earlier placement. "
        "When we returned, the cabinet was open and the compass had moved. "
    )
    text = (
        "Project Gutenberg test fixture\n*** START OF THE PROJECT GUTENBERG EBOOK TEST ***\n\n"
        + "\n\n".join(paragraph for _ in range(32))
        + "\n\n*** END OF THE PROJECT GUTENBERG EBOOK TEST ***"
    )
    book = CatalogBook(999999, "Test Memoir", "Example, Ada", "Personal narratives", "Fiction")

    passage = extract_social_passage(book, text)

    assert passage is not None
    assert passage.speaker == "Clara"
    assert passage.first_person_ratio > 0.5
    assert len(passage.query_terms) >= 2
    assert "Clara" in passage.query


def test_public_domain_fetch_redirects_stay_on_approved_https_hosts() -> None:
    import pytest

    from thoughtpins.memory.public_domain_eval import _assert_gutenberg_url

    _assert_gutenberg_url("https://www.gutenberg.org/cache/epub/1/pg1.txt")
    _assert_gutenberg_url("https://gutenberg.org/ebooks/1.txt.utf-8")
    with pytest.raises(ValueError):
        _assert_gutenberg_url("http://www.gutenberg.org/ebooks/1.txt")
    with pytest.raises(ValueError):
        _assert_gutenberg_url("https://example.com/copied-book.txt")


def test_public_domain_cache_repairs_windows_double_newlines(tmp_path) -> None:
    from thoughtpins.memory.public_domain_eval import CatalogBook, _load_book_text

    paragraph = (
        'I waited in the long west corridor until Clara said, "The silver compass belongs beside the cedar cabinet." '
        "I wrote the instruction down because Clara had corrected the earlier placement."
    )
    original = (
        "The Project Gutenberg eBook of Test\n"
        "*** START OF THE PROJECT GUTENBERG EBOOK TEST ***\n\n"
        + "\n\n".join(paragraph for _ in range(40))
        + "\n\n*** END OF THE PROJECT GUTENBERG EBOOK TEST ***\n"
    )
    corrupted = original.replace("\n", "\n\n")
    book = CatalogBook(999998, "Test Memoir", "Example, Ada", "Personal narratives", "Fiction")
    cache_file = tmp_path / "999998.txt"
    cache_file.write_text(corrupted, encoding="utf-8", newline="\n")

    repaired, downloaded = _load_book_text(book, tmp_path)

    assert downloaded is False
    assert repaired == original
    assert cache_file.read_text(encoding="utf-8") == original
