"""Bounded CPU OCR without downloading model weights at request time."""

from __future__ import annotations

import os
import subprocess


class TesseractReader:
    engine = "tesseract"

    def __init__(self, executable: str) -> None:
        self.executable = executable

    def readtext(self, path: str, *, detail: int = 0, paragraph: bool = True) -> list[str]:
        result = subprocess.run(
            [self.executable, path, "stdout", "-l", "eng", "--psm", "3"],
            capture_output=True,
            timeout=30,
            check=True,
            env={**os.environ, "OMP_THREAD_LIMIT": "1"},
        )
        return [result.stdout.decode("utf-8", errors="replace").strip()]
