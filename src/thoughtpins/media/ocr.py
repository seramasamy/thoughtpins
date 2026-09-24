"""Bounded CPU OCR without downloading model weights at request time."""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any


class TesseractReader:
    engine = "tesseract"
    # Each call runs in a subprocess that can be stopped, which is what lets a
    # caller hold OCR to a time budget.
    supports_timeout = True

    def __init__(self, executable: str) -> None:
        self.executable = executable

    def readtext(self, path: str, *, detail: int = 0, paragraph: bool = True, timeout: float = 30.0) -> list[str]:
        result = subprocess.run(
            [self.executable, path, "stdout", "-l", "eng", "--psm", "3"],
            capture_output=True,
            timeout=timeout,
            check=True,
            env={**os.environ, "OMP_THREAD_LIMIT": "1"},
        )
        return [result.stdout.decode("utf-8", errors="replace").strip()]


class SerializedReader:
    """An OCR engine that is not thread-safe, called one request at a time."""

    supports_timeout = False

    def __init__(self, engine_object: Any, *, engine: str) -> None:
        self._engine_object = engine_object
        self._lock = threading.Lock()
        self.engine = engine

    def readtext(self, path: str, *, detail: int = 0, paragraph: bool = True) -> list[Any]:
        with self._lock:
            return list(self._engine_object.readtext(path, detail=detail, paragraph=paragraph))


def read_image_text(reader: Any, image: Any, *, timeout: float | None = None) -> str:
    """OCR one PIL image with whichever local engine is installed.

    Shared by photo uploads and scanned PDF pages. A timeout is passed only to
    an engine that can honour it -- Tesseract, which the production image ships;
    the optional EasyOCR fallback cannot.
    """

    with tempfile.TemporaryDirectory(prefix="thoughtpins-ocr-") as directory:
        path = Path(directory) / "image.png"
        image.save(path, format="PNG")
        options = {"timeout": timeout} if timeout is not None and getattr(reader, "supports_timeout", False) else {}
        results = reader.readtext(str(path), detail=0, paragraph=True, **options)
    return " ".join(str(item) for item in results).strip()
