from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from thoughtpins.memory.research_budget import AttemptLedger, BudgetExceeded


def ledger(path: Path) -> AttemptLedger:
    return AttemptLedger(path, cap=2, stages={"dev": 1, "final": 1})


def test_crash_reservations_survive_resume_and_protect_final_allocation(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    book = ledger(path)
    assert book.reserve("a", payload_hash="x", stage="dev", amount=0.8)
    resumed = ledger(path)
    assert float(resumed.charged()) == 0.8
    assert not resumed.reserve("a", payload_hash="x", stage="dev", amount=0.8)
    with pytest.raises(BudgetExceeded):
        resumed.reserve("b", payload_hash="y", stage="dev", amount=0.3)
    assert resumed.reserve("c", payload_hash="z", stage="final", amount=1)


def test_actual_usage_releases_only_unused_reservation(tmp_path: Path) -> None:
    book = ledger(tmp_path / "ledger.jsonl")
    book.reserve("a", payload_hash="x", stage="dev", amount=0.8)
    book.settle("a", actual=0.2, status="ok", usage={"prompt_tokens": 100}, response_hash="r")
    assert float(book.charged()) == 0.2
    with pytest.raises(ValueError, match="already settled"):
        book.settle("a", actual=0, status="ok", usage={}, response_hash="r")
    with pytest.raises(ValueError, match="semantic"):
        book.reserve("a", payload_hash="different", stage="dev", amount=0.8)
    assert ledger(book.path).summary() == book.summary()


def test_unknown_failure_keeps_reservation_and_tamper_fails_closed(tmp_path: Path) -> None:
    book = ledger(tmp_path / "ledger.jsonl")
    book.reserve("a", payload_hash="x", stage="dev", amount=0.8)
    book.settle("a", actual=None, status="timeout", usage={}, response_hash="r")
    assert float(book.charged()) == 0.8
    book.path.write_text(book.path.read_text().replace('"0.8"', '"0.0"'))
    with pytest.raises(ValueError, match="Corrupt"):
        ledger(book.path)


def test_concurrent_reservations_are_atomic(tmp_path: Path) -> None:
    book = ledger(tmp_path / "ledger.jsonl")

    def attempt(i: int) -> bool:
        try:
            return book.reserve(str(i), payload_hash=str(i), stage="dev", amount=0.4)
        except BudgetExceeded:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(attempt, range(10))) == 2
    assert float(book.charged()) == 0.8


def test_underestimated_usage_blocks_further_calls(tmp_path: Path) -> None:
    book = ledger(tmp_path / "ledger.jsonl")
    book.reserve("a", payload_hash="x", stage="dev", amount=0.1)
    book.settle("a", actual=0.2, status="ok", usage={}, response_hash="r")
    with pytest.raises(BudgetExceeded, match="overrun"):
        book.reserve("b", payload_hash="y", stage="dev", amount=0.1)
