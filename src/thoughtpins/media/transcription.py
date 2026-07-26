"""Provider-neutral voice-note transcription with ephemeral temporary files."""

from __future__ import annotations

import mimetypes
import tempfile
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
from loguru import logger

from thoughtpins.config import config
from thoughtpins.media.extraction_types import MediaExtraction

_SAFE_SUFFIXES = {".aac", ".flac", ".m4a", ".mp3", ".mp4", ".oga", ".ogg", ".wav", ".webm"}
_MEDIA_TYPES = {
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".mp4": "audio/mp4",
    ".oga": "audio/ogg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".webm": "audio/webm",
}


def transcribe_audio(content: bytes, *, suffix: str = ".ogg", language: str | None = None) -> MediaExtraction:
    """Transcribe one user-initiated recording without retaining its bytes."""

    if not content:
        return MediaExtraction(kind="audio", error="empty_audio")
    normalized_suffix = _normalize_suffix(suffix)
    if config.TRANSCRIPTION_PROVIDER == "hosted":
        return _transcribe_hosted(content, suffix=normalized_suffix, language=language)
    if config.TRANSCRIPTION_PROVIDER == "local":
        return _transcribe_local(content, suffix=normalized_suffix, language=language)
    logger.warning("Audio transcription mode is invalid")
    return MediaExtraction(kind="audio", error="transcription_not_configured")


def _transcribe_local(content: bytes, *, suffix: str, language: str | None) -> MediaExtraction:
    tmp_path: Path | None = None
    try:
        model = _get_local_model()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        options: dict[str, Any] = {"fp16": False}
        if language:
            options["language"] = language
        with _local_inference_lock:
            result = model.transcribe(str(tmp_path), **options)
        text = str(result.get("text") or "").strip()
        detected_language = str(result.get("language") or language or "").strip() or None
        if not _has_recognizable_speech(result, text):
            return MediaExtraction(
                kind="audio",
                metadata={"processing": "local", "language": detected_language, "speech_detected": False},
                error="no_speech_detected",
            )
        return MediaExtraction(
            text=text,
            kind="audio",
            metadata={"processing": "local", "language": detected_language, "speech_detected": True},
        )
    except ImportError:
        logger.debug("Local audio transcription dependency is unavailable")
        return MediaExtraction(kind="audio", error="missing_transcription_dependency")
    except Exception as exc:
        logger.warning("Local audio transcription failed: {}", type(exc).__name__)
        return MediaExtraction(kind="audio", error="transcription_failed")
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def _transcribe_hosted(content: bytes, *, suffix: str, language: str | None) -> MediaExtraction:
    if not config.TRANSCRIPTION_API_KEY:
        return MediaExtraction(kind="audio", error="transcription_not_configured")
    media_type = _MEDIA_TYPES.get(suffix) or mimetypes.types_map.get(suffix, "application/octet-stream")
    endpoint = urljoin(config.TRANSCRIPTION_BASE_URL.rstrip("/") + "/", "audio/transcriptions")
    form = {"model": config.TRANSCRIPTION_MODEL}
    if language:
        form["language"] = language
    try:
        with httpx.Client(timeout=config.TRANSCRIPTION_TIMEOUT_SECONDS, follow_redirects=False) as client:
            response = client.post(
                endpoint,
                headers={"Authorization": f"Bearer {config.TRANSCRIPTION_API_KEY}"},
                files={"file": (f"voice-note{suffix}", content, media_type)},
                data=form,
            )
        response.raise_for_status()
        payload = response.json()
        text = str(payload.get("text") or "").strip() if isinstance(payload, dict) else ""
        detected_language = (
            str(payload.get("language") or language or "").strip() or None if isinstance(payload, dict) else language
        )
        return MediaExtraction(
            text=text,
            kind="audio",
            metadata={
                "processing": "external",
                "language": detected_language,
                "speech_detected": bool(text),
            },
            error=None if text else "no_speech_detected",
        )
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Hosted audio transcription failed: {}", type(exc).__name__)
        return MediaExtraction(kind="audio", error="transcription_failed")


def _normalize_suffix(suffix: str) -> str:
    candidate = (suffix or ".audio").lower()
    if not candidate.startswith("."):
        candidate = f".{candidate}"
    return candidate if candidate in _SAFE_SUFFIXES else ".audio"


def _has_recognizable_speech(result: dict[str, Any], text: str) -> bool:
    if not text:
        return False
    segments = result.get("segments")
    if not isinstance(segments, list) or not segments:
        return True
    probabilities = [float(segment.get("no_speech_prob", 0.0)) for segment in segments if isinstance(segment, dict)]
    return not probabilities or any(probability < 0.85 for probability in probabilities)


_local_model: Any | None = None
_local_model_name: str | None = None
_local_model_lock = threading.Lock()
_local_inference_lock = threading.Lock()


def _get_local_model() -> Any:
    global _local_model, _local_model_name
    requested_model = config.TRANSCRIPTION_LOCAL_MODEL
    if _local_model is not None and _local_model_name == requested_model:
        return _local_model
    with _local_model_lock:
        if _local_model is None or _local_model_name != requested_model:
            import whisper

            _local_model = whisper.load_model(requested_model)
            _local_model_name = requested_model
            logger.info("Local voice transcription model loaded")
    return _local_model
