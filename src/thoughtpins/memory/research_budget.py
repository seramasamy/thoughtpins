"""Durable, provider-neutral attempt accounting for offline experiments.

A caller must exclusively own the journal across processes. Threads share one
instance. An interrupted or unknown-cost request remains charged at its full
reservation. This module never reads credentials or submits requests.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any


def canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _money(value: str | float | int | Decimal) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError("Cost must be finite and nonnegative")
    return result


class BudgetExceeded(ValueError):
    """A request cannot be sent within the registered spending limits."""


class AttemptLedger:
    """Append-only hash-chained journal, with reservations persisted before send."""

    def __init__(self, path: Path, *, cap: float, stages: dict[str, float]) -> None:
        self.path = path
        self.cap = _money(cap)
        self.stages = {key: _money(value) for key, value in stages.items()}
        if sum(self.stages.values()) > self.cap:
            raise ValueError("Stage allocations exceed total cap")
        self._lock = threading.RLock()
        self.attempts: dict[str, dict[str, Any]] = {}
        self.tail = "0" * 64
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                event = json.loads(line)
                checksum = event.pop("sha256")
                if event["previous"] != self.tail or canonical_hash(event) != checksum:
                    raise ValueError("Corrupt budget journal; fail closed")
                self._apply(event)
                self.tail = checksum

    def _apply(self, event: dict[str, Any]) -> None:
        request_id = event["request_id"]
        if event["event"] == "reserve":
            if request_id in self.attempts:
                raise ValueError("Duplicate attempt reservation")
            self.attempts[request_id] = dict(event)
        elif event["event"] == "settle":
            attempt = self.attempts[request_id]
            if attempt["event"] != "reserve":
                raise ValueError("Attempt was already settled")
            attempt.update(event)
        else:
            raise ValueError("Unknown budget event")

    def _append(self, event: dict[str, Any]) -> None:
        event.update(utc=datetime.now(timezone.utc).isoformat(), previous=self.tail)
        checksum = canonical_hash(event)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps({**event, "sha256": checksum}, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._apply(event)
        self.tail = checksum

    def charged(self, stage: str | None = None) -> Decimal:
        with self._lock:
            return sum(
                (
                    _money(a.get("charged_usd", a["reserved_usd"]))
                    for a in self.attempts.values()
                    if stage is None or a["stage"] == stage
                ),
                Decimal(0),
            )

    def reserve(self, request_id: str, *, payload_hash: str, stage: str, amount: float) -> bool:
        """Return false for a previously attempted identical job, without resending."""
        with self._lock:
            if request_id in self.attempts:
                if self.attempts[request_id]["payload_hash"] != payload_hash:
                    raise ValueError("Resumed request identity has changed semantic input")
                return False
            cost = _money(amount)
            if stage not in self.stages:
                raise ValueError("Unregistered budget stage")
            if any(a.get("overrun") for a in self.attempts.values()):
                raise BudgetExceeded("Earlier estimate overrun requires audit before more calls")
            if self.charged() + cost > self.cap or self.charged(stage) + cost > self.stages[stage]:
                raise BudgetExceeded("Conservative reservations exceed budget")
            self._append(
                {
                    "event": "reserve",
                    "request_id": request_id,
                    "payload_hash": payload_hash,
                    "stage": stage,
                    "reserved_usd": str(cost),
                }
            )
            return True

    def settle(
        self, request_id: str, *, actual: float | None, status: str, usage: dict[str, Any], response_hash: str
    ) -> None:
        with self._lock:
            attempt = self.attempts[request_id]
            if attempt["event"] != "reserve":
                raise ValueError("Attempt was already settled")
            reserved = _money(attempt["reserved_usd"])
            charged = reserved if actual is None else _money(actual)
            self._append(
                {
                    "event": "settle",
                    "request_id": request_id,
                    "charged_usd": str(charged),
                    "status": status,
                    "usage": usage,
                    "response_hash": response_hash,
                    "cost_basis": "reservation_unknown_usage" if actual is None else "reported_usage_no_cache_discount",
                    "overrun": charged > reserved,
                }
            )

    def summary(self) -> dict[str, Any]:
        return {
            "charged_usd": float(self.charged()),
            "cap_usd": float(self.cap),
            "by_stage": {key: float(self.charged(key)) for key in self.stages},
            "attempts": len(self.attempts),
            "unsettled": sum(a["event"] == "reserve" for a in self.attempts.values()),
            "tail_sha256": self.tail,
        }
