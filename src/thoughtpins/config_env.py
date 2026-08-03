"""Reading configuration values out of the environment.

Parsing only: every function here answers "what did the operator set", never
"what should the service do about it". Split out of config.py, which had grown
past its size budget with the two of them mixed together.
"""

from __future__ import annotations

import os
from typing import Iterable


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _env_any(keys: Iterable[str], default: str = "") -> str:
    for key in keys:
        value = _env(key)
        if value:
            return value
    return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key, "").strip().lower()
    if val in ("true", "1", "yes", "on"):
        return True
    if val in ("false", "0", "no", "off"):
        return False
    return default


def _env_int_list(key: str) -> list[int]:
    values: list[int] = []
    for raw in _env(key).split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            values.append(int(raw))
        except ValueError:
            continue
    return values


def _env_str_list(key: str) -> list[str]:
    return [value.strip() for value in _env(key).split(",") if value.strip()]
