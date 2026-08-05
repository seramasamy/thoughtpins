"""Retry pacing against a shared, rate-limited provider.

The delay used to be a constant. That is the wrong shape twice: a provider
returning 429 needs progressively more room, and a fixed pause puts every
concurrent worker back on the wire at the same instant, so one rate-limit event
reconverges into the next.
"""

from __future__ import annotations

import random
import statistics

from thoughtpins.llm.openai_compatible_client import (
    _RETRY_BASE_SECONDS,
    _RETRY_MAX_SECONDS,
    _retry_delay_seconds,
)


def _ceiling(attempt: int) -> float:
    return min(_RETRY_MAX_SECONDS, _RETRY_BASE_SECONDS * (2**attempt))


# --------------------------------------------------------------------- bounds


def test_a_delay_is_never_negative_and_never_unbounded():
    rng = random.Random(7)
    for attempt in range(12):
        delay = _retry_delay_seconds(attempt, rng=rng)
        assert 0.0 <= delay <= _RETRY_MAX_SECONDS, (attempt, delay)


def test_the_window_doubles_until_it_reaches_the_ceiling():
    rng = random.Random(11)
    for attempt in range(6):
        samples = [_retry_delay_seconds(attempt, rng=rng) for _ in range(400)]
        assert max(samples) <= _ceiling(attempt) + 1e-9


def test_the_ceiling_stops_the_doubling():
    """Without a cap, attempt 10 would ask a user to wait four minutes."""
    rng = random.Random(3)
    far = [_retry_delay_seconds(20, rng=rng) for _ in range(200)]
    assert max(far) <= _RETRY_MAX_SECONDS


def test_a_negative_attempt_does_not_invert_the_window():
    assert 0.0 <= _retry_delay_seconds(-5, rng=random.Random(1)) <= _RETRY_BASE_SECONDS


# ------------------------------------------------------------------ behaviour


def test_later_attempts_wait_longer_on_average():
    """The property a fixed delay lacked: back off, do not just pause."""
    rng = random.Random(5)
    early = statistics.mean(_retry_delay_seconds(0, rng=rng) for _ in range(2000))
    later = statistics.mean(_retry_delay_seconds(4, rng=rng) for _ in range(2000))
    assert later > early * 4


def test_concurrent_workers_do_not_retry_in_lockstep():
    """Full jitter exists to decorrelate the herd. Distinct workers hitting the
    same attempt number must spread across the window, not stack on one point."""
    rng = random.Random(13)
    herd = [_retry_delay_seconds(3, rng=rng) for _ in range(1000)]
    window = _ceiling(3)

    assert len(set(herd)) > 900, "delays are not actually being jittered"
    # A uniform draw fills the window; a constant delay would occupy one bucket.
    occupied_tenths = {int(delay / window * 10) for delay in herd}
    assert len(occupied_tenths) >= 9, f"herd clustered into {len(occupied_tenths)} of 10 buckets"


def test_the_draw_covers_the_whole_window_not_just_its_top():
    """Equal-jitter schemes only halve the herd; full jitter spreads it flat."""
    rng = random.Random(17)
    window = _ceiling(3)
    herd = [_retry_delay_seconds(3, rng=rng) for _ in range(2000)]
    assert min(herd) < window * 0.05, "no short delays drawn; this is not full jitter"
    assert max(herd) > window * 0.95, "no long delays drawn"


def test_the_schedule_is_reproducible_for_a_seeded_generator():
    """So a flaky-retry investigation can be replayed."""
    first = [_retry_delay_seconds(i, rng=random.Random(99)) for i in range(6)]
    second = [_retry_delay_seconds(i, rng=random.Random(99)) for i in range(6)]
    assert first == second
