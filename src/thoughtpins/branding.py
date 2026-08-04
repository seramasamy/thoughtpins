"""The mark, drawn for a terminal.

A startup banner is the first thing anyone sees when they run this, so it is
worth getting right — but it is decoration, and decoration must never be able
to stop a server booting. Every function here degrades: no colour when the
output is piped, plain ASCII when the console cannot encode block glyphs, and
nothing at all rather than an exception.
"""

from __future__ import annotations

import os
import sys
from typing import Protocol


class Console(Protocol):
    """The little of a stream this module actually touches.

    `encoding` is a read-only property rather than an attribute so that
    `sys.stdout`, which exposes it as a property, satisfies this.
    """

    @property
    def encoding(self) -> str: ...
    def write(self, text: str, /) -> int: ...
    def isatty(self) -> bool: ...


# Drawn as a left half and mirrored, so the mark cannot drift out of symmetry
# the way hand-spacing does. The two centre columns are the brain's stem.
_HALF = (
    "        ▄▄▄▄",
    "     ▄▄█████",
    "   ▄████▀▀ █",
    "  ███▀ ▄▄  █",
    "  ██▌  ██  █",
    "  ██▌  ▀▀  █",
    "  ███▄ ▄▄  █",
    "   ▀████▄▄ █",
    "     ▀▀█████",
    "        ▀███",
    "         ▀██",
    "          ▀█",
    "           ▀",
)
_MIRROR = str.maketrans("▌▐", "▐▌")

MARK: tuple[str, ...] = tuple(half + half[::-1].translate(_MIRROR) for half in _HALF)

# A map pin holds a place; the fallback keeps the silhouette when the console
# has no block glyphs, which is the part that still reads as the logo.
MARK_ASCII: tuple[str, ...] = (
    "      .-'''''-.      ",
    "    .'  _   _  '.    ",
    "   /   (_) (_)   \\   ",
    "  |     | | |     |  ",
    "   \\    | | |    /   ",
    "    '.  |_|_|  .'    ",
    "      '-.___.-'      ",
    "         \\ /         ",
    "          V          ",
)

_ORANGE = "\033[38;5;209m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def supports_colour(stream: Console | None = None) -> bool:
    """Colour only into a real terminal, and never against NO_COLOR."""
    target: Console = stream if stream is not None else sys.stdout
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    isatty = getattr(target, "isatty", None)
    return bool(callable(isatty) and isatty())


def _encodable(lines: tuple[str, ...], stream: Console) -> bool:
    """Whether this console can actually render the glyphs."""
    encoding = getattr(stream, "encoding", None) or "ascii"
    try:
        "\n".join(lines).encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def banner(version: str, *, colour: bool = False, art: tuple[str, ...] | None = None) -> str:
    """The mark beside the wordmark, ready to print."""
    art = art if art is not None else MARK
    tint, dim, off = (_ORANGE, _DIM, _RESET) if colour else ("", "", "")

    right = [
        "",
        "",
        f"{'Thought Pins'}",
        f"{dim}Your memory, connected.{off}",
        "",
        f"{dim}v{version}{off}",
    ]
    right += [""] * (len(art) - len(right))

    width = max(len(line) for line in art)
    rows = [f"  {tint}{left:<{width}}{off}   {text}".rstrip() for left, text in zip(art, right, strict=True)]
    return "\n".join(["", *rows, ""])


def print_banner(version: str, stream: Console | None = None) -> None:
    """Print the banner, or quietly print nothing if the console objects."""
    target: Console = stream if stream is not None else sys.stdout
    try:
        art = MARK if _encodable(MARK, target) else MARK_ASCII
        target.write(banner(version, colour=supports_colour(target), art=art) + "\n")
        flush = getattr(target, "flush", None)
        if callable(flush):
            flush()
    except Exception:  # noqa: BLE001 - a banner must never stop a boot
        pass
