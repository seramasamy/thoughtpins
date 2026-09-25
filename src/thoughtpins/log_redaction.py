"""Keep exception messages out of log output, and keep what debugging needs.

An exception's message can quote what it failed on: SQLAlchemy prints the
statement and its parameters, pydantic and JSON errors their input, a provider
error the request. On this service that is journal text. The log-privacy gate
bans printing an exception at a call site, but ``logger.exception()`` attaches
the traceback by itself, and a traceback's last line is the message.

The patcher swaps the logged exception for a stand-in with the same name and
module whose message is withheld, rebuilt along the whole cause/context chain
and through exception groups with the original tracebacks. Every sink -- text,
JSON, the Sentry handler -- still shows each exception's type and every frame;
none shows its text. Each stand-in's original is remembered for as long as the
stand-in lives, so error reporting can recognise two reports of one failure.
"""

from __future__ import annotations

import contextlib
import weakref
from typing import Any

WITHHELD = "<message withheld: exception text can quote user content>"
_MAX_CHAIN = 16
# Keyed weakly by the original class, and the stand-ins refer to it only by
# name, so a class created at run time can still be collected.
_stand_in_types: weakref.WeakKeyDictionary[type, dict[bool, type]] = weakref.WeakKeyDictionary()
# Keyed weakly by the stand-in, which is always a Python-level class and so can
# be weakly referenced; a built-in exception such as RuntimeError cannot be.
_originals: weakref.WeakKeyDictionary[BaseException, BaseException] = weakref.WeakKeyDictionary()


class WithheldException(Exception):
    """Used when a faithful stand-in cannot be built; never shows a message."""

    def __str__(self) -> str:
        return WITHHELD


def withhold_exception_messages(record: Any) -> None:
    """Loguru patcher: replace the record's exception with a message-free stand-in.

    Loguru does not guard patchers, so this never raises: a failure here would
    escape from the caller's own ``logger.exception()`` call.
    """

    exception = record.get("exception")
    if exception is None or exception.value is None or _is_stand_in(exception.value):
        # Nothing to withhold, or withheld already (the patcher ran twice).
        return
    try:
        stand_in = _stand_in(exception.value, depth=0, seen=set())
    except Exception:
        stand_in = WithheldException()
        stand_in.__traceback__ = exception.value.__traceback__
        with contextlib.suppress(Exception):
            _remember_original(stand_in, exception.value)
    record["exception"] = exception._replace(value=stand_in)


def original_exception(value: BaseException) -> BaseException:
    """The exception a stand-in replaced, or the exception itself."""

    try:
        return _originals.get(value, value)
    except TypeError:
        # It cannot be weakly referenced, so it is not a stand-in.
        return value


def _stand_in(value: BaseException, *, depth: int, seen: set[int]) -> BaseException:
    seen.add(id(value))
    if isinstance(value, BaseExceptionGroup) and depth < _MAX_CHAIN:
        # A group's children are rebuilt too, so their types and frames survive
        # the way a single exception's do.
        children = [_stand_in(child, depth=depth + 1, seen=seen) for child in value.exceptions]
        stand_in: BaseException = _stand_in_type(type(value), group=True)(WITHHELD, children)
    else:
        stand_in = _stand_in_type(type(value), group=False)()
    stand_in.__traceback__ = value.__traceback__
    _remember_original(stand_in, value)
    if depth < _MAX_CHAIN:
        cause, context = value.__cause__, value.__context__
        if cause is not None and id(cause) not in seen:
            stand_in.__cause__ = _stand_in(cause, depth=depth + 1, seen=seen)
        if context is not None and id(context) not in seen:
            stand_in.__context__ = _stand_in(context, depth=depth + 1, seen=seen)
    # Setting __cause__ turns suppression on; restore what the original had.
    stand_in.__suppress_context__ = value.__suppress_context__
    return stand_in


def _is_stand_in(value: BaseException) -> bool:
    try:
        return value in _originals
    except TypeError:
        # Unhashable -- a dataclass exception, say -- so never one of these.
        return False


def _remember_original(stand_in: BaseException, original: BaseException) -> None:
    _originals[stand_in] = original_exception(original)


def _stand_in_type(original: type, *, group: bool) -> type:
    by_kind = _stand_in_types.setdefault(original, {})
    stand_in = by_kind.get(group)
    if stand_in is None:
        qualname = original.__qualname__
        stand_in = type(
            original.__name__,
            (ExceptionGroup,) if group else (Exception,),
            {
                "__module__": original.__module__,
                "__qualname__": qualname,
                "__str__": lambda self: WITHHELD,
                "__repr__": lambda self: f"{qualname}({WITHHELD!r})",
            },
        )
        by_kind[group] = stand_in
    return stand_in
