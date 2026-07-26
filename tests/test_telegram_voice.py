from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from thoughtpins.uploads import UploadIngestOutcome


class _StatusMessage:
    def __init__(self) -> None:
        self.edits: list[str] = []

    async def edit_text(self, text: str) -> None:
        self.edits.append(text)


class _VoiceMessage:
    def __init__(self) -> None:
        self.chat_id = "voice-adapter-chat"
        self.message_id = 17
        self.from_user = SimpleNamespace(id=901)
        self.voice = SimpleNamespace(file_id="voice-file", duration=4)
        self.status = _StatusMessage()

    async def reply_text(self, _text: str) -> _StatusMessage:
        return self.status


def _update() -> SimpleNamespace:
    return SimpleNamespace(message=_VoiceMessage())


def _outcome(*, retained: bool = False, status: str = "completed") -> UploadIngestOutcome:
    return UploadIngestOutcome(
        status=status,
        route_type="journal_upload" if status != "needs_text" else "upload_needs_text",
        filename="telegram-voice-note.ogg",
        media_kind="audio",
        destination="journal",
        extraction_status="processed" if status != "needs_text" else "no_speech_detected",
        extracted_chars=24 if status != "needs_text" else 0,
        attachment_saved=retained,
        voice_asset_id="voice-asset" if retained else None,
        entry_id="voice-entry" if status != "needs_text" else None,
    )


def test_telegram_voice_uses_shared_ingestion_and_content_free_audit(isolated_db, monkeypatch):
    from thoughtpins.bot import voice as bot_voice
    from thoughtpins.db import AuditLog
    from thoughtpins.store import get_session

    captured: dict[str, object] = {}

    def fake_ingest(session, **kwargs):
        captured.update(kwargs)
        return _outcome(retained=True)

    monkeypatch.setattr(bot_voice, "ingest_upload", fake_ingest)
    result = bot_voice._ingest_voice(_update(), b"private-audio-canary")

    assert result.voice_asset_id == "voice-asset"
    assert captured["content"] == b"private-audio-canary"
    assert captured["surface"] == "telegram"
    assert captured["conversation_id"] == "voice-adapter-chat"
    assert captured["message_id"] == "17"
    assert captured["author_user_id"] == "901"

    session = get_session()
    try:
        event = session.query(AuditLog).filter_by(action="voice.note.processed").one()
        encoded = json.dumps(event.metadata_json, sort_keys=True)
        assert "private-audio-canary" not in encoded
        assert "transcript" not in encoded.lower()
        assert event.metadata_json["surface"] == "telegram"
        assert event.metadata_json["voice_retained"] is True
    finally:
        session.close()


@pytest.mark.asyncio
async def test_telegram_voice_reports_ephemeral_and_no_speech_states(monkeypatch):
    from thoughtpins.bot import voice as bot_voice

    class VoiceFile:
        async def download_as_bytearray(self):
            return bytearray(b"audio")

    class Bot:
        async def get_file(self, _file_id: str):
            return VoiceFile()

    context = SimpleNamespace(bot=Bot())

    ephemeral_update = _update()
    monkeypatch.setattr(bot_voice, "_ingest_voice", lambda *args: _outcome())
    await bot_voice.handle_voice_message(ephemeral_update, context)
    assert "discarded after transcription" in ephemeral_update.message.status.edits[-1]

    silent_update = _update()
    monkeypatch.setattr(bot_voice, "_ingest_voice", lambda *args: _outcome(status="needs_text"))
    await bot_voice.handle_voice_message(silent_update, context)
    assert "could not hear enough speech" in silent_update.message.status.edits[-1]
