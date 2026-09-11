from __future__ import annotations

from pathlib import Path

import httpx

from thoughtpins.media import extract_document_text, extract_image_text, transcribe_audio
from thoughtpins.media import extraction as media_extraction
from thoughtpins.media import transcription as media_transcription


def test_text_document_extraction_returns_utf8_text():
    result = extract_document_text(b"Line one\nLine two", ".txt")
    assert result.ok
    assert result.text == "Line one\nLine two"
    assert result.metadata["engine"] == "utf8"


def test_binary_document_without_reader_fails_closed():
    result = extract_document_text(bytes([0, 1, 2, 3, 4, 5]) * 20, ".bin")
    assert not result.ok
    assert result.error == "unsupported_binary_document"


def test_missing_optional_media_dependencies_are_scoped(monkeypatch):
    def missing_dependency():
        raise ImportError("optional dependency unavailable")

    monkeypatch.setattr(media_extraction, "_get_ocr_reader", missing_dependency)
    monkeypatch.setattr(media_transcription, "_get_local_model", missing_dependency)

    image = extract_image_text(b"not actually an image", suffix=".jpg")
    audio = transcribe_audio(b"not actually audio", suffix=".ogg")
    assert image.error == "missing_ocr_dependency"
    assert audio.error == "missing_transcription_dependency"


def test_local_transcription_auto_detects_language_and_removes_temp_file(monkeypatch):
    from thoughtpins.config import config

    captured: dict[str, object] = {}

    class FakeModel:
        def transcribe(self, path: str, **options):
            captured["path"] = path
            captured["options"] = options
            assert Path(path).is_file()
            return {
                "text": "Bonjour Maya",
                "language": "fr",
                "segments": [{"no_speech_prob": 0.01}],
            }

    monkeypatch.setattr(config, "TRANSCRIPTION_PROVIDER", "local")
    monkeypatch.setattr(media_transcription, "_get_local_model", lambda: FakeModel())
    result = transcribe_audio(b"audio fixture", suffix=".wav")

    assert result.ok
    assert result.text == "Bonjour Maya"
    assert result.metadata == {"processing": "local", "language": "fr", "speech_detected": True}
    options = captured["options"]
    assert isinstance(options, dict)
    assert "language" not in options
    assert not Path(str(captured["path"])).exists()


def test_local_transcription_rejects_silence_hallucination(monkeypatch):
    from thoughtpins.config import config

    class SilentModel:
        def transcribe(self, path: str, **options):
            return {
                "text": "Thank you for watching.",
                "language": "en",
                "segments": [{"no_speech_prob": 0.99}],
            }

    monkeypatch.setattr(config, "TRANSCRIPTION_PROVIDER", "local")
    monkeypatch.setattr(media_transcription, "_get_local_model", lambda: SilentModel())
    result = transcribe_audio(b"silence fixture", suffix=".wav")
    assert not result.ok
    assert result.text == ""
    assert result.error == "no_speech_detected"


def test_unknown_transcription_mode_fails_closed(monkeypatch):
    from thoughtpins.config import config

    monkeypatch.setattr(config, "TRANSCRIPTION_PROVIDER", "invalid")
    result = transcribe_audio(b"audio fixture", suffix=".wav")
    assert not result.ok
    assert result.error == "transcription_not_configured"


def test_transcription_health_is_provider_neutral(monkeypatch):
    from thoughtpins.config import config
    from thoughtpins.runtime_health import transcription_health

    monkeypatch.setattr(config, "TRANSCRIPTION_PROVIDER", "hosted")
    monkeypatch.setattr(config, "TRANSCRIPTION_API_KEY", "configured")
    monkeypatch.setattr(config, "TRANSCRIPTION_BASE_URL", "https://transcription.example/v1")
    monkeypatch.setattr(config, "TRANSCRIPTION_MODEL", "configured-model")
    health = transcription_health()
    assert health == {"status": "configured", "processing": "external"}
    assert "provider" not in health
    assert "model" not in health


def test_hosted_transcription_is_provider_neutral_and_does_not_leak_configuration(monkeypatch):
    from thoughtpins.config import config

    request: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"text": "A clear hosted transcript", "language": "en"}

    class FakeClient:
        def __init__(self, **kwargs):
            request["client"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, endpoint, **kwargs):
            request["endpoint"] = endpoint
            request["post"] = kwargs
            return FakeResponse()

    monkeypatch.setattr(config, "TRANSCRIPTION_PROVIDER", "hosted")
    monkeypatch.setattr(config, "TRANSCRIPTION_API_KEY", "private-test-key")
    monkeypatch.setattr(config, "TRANSCRIPTION_BASE_URL", "https://speech.example.test/v1")
    monkeypatch.setattr(config, "TRANSCRIPTION_MODEL", "private-model-name")
    monkeypatch.setattr(media_transcription.httpx, "Client", FakeClient)

    result = transcribe_audio(b"audio fixture", suffix="m4a")
    assert result.ok
    assert result.metadata == {"processing": "external", "language": "en", "speech_detected": True}
    assert "private-test-key" not in repr(result)
    assert "private-model-name" not in repr(result)
    assert request["endpoint"] == "https://speech.example.test/v1/audio/transcriptions"


def test_hosted_transcription_failure_is_generic(monkeypatch):
    from thoughtpins.config import config

    class FailingClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, endpoint, **kwargs):
            raise httpx.ConnectError("sensitive upstream detail")

    monkeypatch.setattr(config, "TRANSCRIPTION_PROVIDER", "hosted")
    monkeypatch.setattr(config, "TRANSCRIPTION_API_KEY", "private-test-key")
    monkeypatch.setattr(media_transcription.httpx, "Client", FailingClient)
    result = transcribe_audio(b"audio fixture", suffix=".m4a")
    assert result.error == "transcription_failed"
    assert "sensitive" not in repr(result)
