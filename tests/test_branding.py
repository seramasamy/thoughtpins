"""The startup banner is decoration, so the rule it must obey is that nothing
about it can stop a server booting — not a pipe, not a legacy code page, not a
stream that raises on write.
"""

from __future__ import annotations

import io

from thoughtpins.branding import MARK, MARK_ASCII, banner, print_banner, supports_colour


class Tty(io.StringIO):
    encoding = "utf-8"

    def isatty(self) -> bool:
        return True


class Cp1252(io.StringIO):
    encoding = "cp1252"

    def isatty(self) -> bool:
        return True


# ------------------------------------------------------------------- the mark


def test_the_mark_is_a_rectangle():
    """Ragged rows would shear the logo in any monospace font."""
    assert len({len(line) for line in MARK}) == 1
    assert len({len(line) for line in MARK_ASCII}) == 1


def test_the_mark_is_symmetric():
    width = len(MARK[0])
    for row in MARK:
        left, right = row[: width // 2], row[width // 2 :]
        assert left == right[::-1].translate(str.maketrans("▌▐", "▐▌")), row


# ------------------------------------------------------------------ rendering


def test_the_banner_names_the_product_and_version():
    text = banner("1.2.3")
    assert "Thought Pins" in text
    assert "v1.2.3" in text


def test_no_colour_when_the_output_is_not_a_terminal():
    """Escape codes in a log file or a pipe are noise, not colour."""
    assert supports_colour(io.StringIO()) is False
    assert "\033[" not in banner("1.0.0", colour=False)


def test_no_colour_when_NO_COLOR_is_set(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    assert supports_colour(Tty()) is False


def test_colour_into_a_real_terminal(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("TERM", raising=False)
    assert supports_colour(Tty()) is True


# ------------------------------------------------------------------ degrading


def test_a_legacy_code_page_gets_the_ascii_mark():
    """cp1252 cannot encode block glyphs; it must not raise, and must still
    show something shaped like the logo."""
    stream = Cp1252()
    print_banner("1.0.0", stream=stream)
    written = stream.getvalue()
    assert "Thought Pins" in written
    assert "█" not in written
    written.encode("cp1252")  # would raise if the fallback leaked glyphs


def test_a_utf8_terminal_gets_the_block_mark():
    stream = Tty()
    print_banner("1.0.0", stream=stream)
    assert "█" in stream.getvalue()


def test_a_stream_that_explodes_does_not_take_the_server_with_it():
    class Hostile(io.StringIO):
        encoding = "utf-8"

        def write(self, _s):
            raise OSError("broken pipe")

    print_banner("1.0.0", stream=Hostile())  # must not raise
