"""The resolution memo has to stay bounded in a long-lived worker.

Its key includes a hash of the passage, which is correct — "Apple" means
different things in different entries — but it also means keys are effectively
unique per entry. Unbounded, that is a dict in a Celery worker that grows for
the life of the process and never releases.
"""

from __future__ import annotations

import threading

import pytest

from thoughtpins.ingestion import entity_resolution as er


@pytest.fixture(autouse=True)
def clean_cache():
    er._resolution_cache.clear()
    yield
    er._resolution_cache.clear()


def test_a_stored_resolution_can_be_read_back():
    er._cache_put(("nyc", "new york city", 1), "New York City")
    assert er._cache_get(("nyc", "new york city", 1)) == "New York City"


def test_an_absent_key_reads_as_none():
    assert er._cache_get(("nothing", "here", 0)) is None


def test_the_cache_cannot_grow_without_bound():
    """The property that matters: ingestion runs forever, memory does not."""
    for i in range(er._RESOLUTION_CACHE_MAX_ENTRIES * 3):
        er._cache_put((f"surface{i}", f"canonical{i}", i), f"Entity {i}")
    assert er.resolution_cache_size() == er._RESOLUTION_CACHE_MAX_ENTRIES


def test_eviction_discards_the_least_recently_used():
    limit = er._RESOLUTION_CACHE_MAX_ENTRIES
    for i in range(limit):
        er._cache_put((f"s{i}", f"c{i}", i), f"E{i}")

    # Touch the oldest so it is no longer the least recently used.
    assert er._cache_get(("s0", "c0", 0)) == "E0"
    er._cache_put(("overflow", "overflow", -1), "Overflow")

    assert er._cache_get(("s0", "c0", 0)) == "E0", "a recently read entry was evicted"
    assert er._cache_get(("s1", "c1", 1)) is None, "the true LRU entry survived"


def test_concurrent_writers_do_not_corrupt_the_bound():
    """Ingestion is threaded, so eviction runs under contention."""

    def hammer(offset: int) -> None:
        for i in range(500):
            er._cache_put((f"t{offset}-{i}", "c", i), "value")

    threads = [threading.Thread(target=hammer, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert er.resolution_cache_size() <= er._RESOLUTION_CACHE_MAX_ENTRIES


def test_a_context_free_answer_is_never_reused_across_passages():
    """Guards the reason the key is shaped this way. 'Apple' in one entry must
    not answer for 'Apple' in another, or resolution becomes confidently wrong."""
    fruit_passage, laptop_passage = 111, 222
    er._cache_put(("apple", "apple the fruit", fruit_passage), "Apple the fruit")

    assert er._cache_get(("apple", "apple the fruit", laptop_passage)) is None
