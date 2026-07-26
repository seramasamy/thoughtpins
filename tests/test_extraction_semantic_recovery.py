from __future__ import annotations

from thoughtpins.ingestion.extraction_recovery import ensure_durable_memory
from thoughtpins.llm import ExtractedActionItem, ExtractedEntity, ExtractedMemory, ExtractionResult


class StubExtractionClient:
    def __init__(self, payload: dict | Exception):
        self.payload = payload
        self.calls = 0

    def extract_json(self, *_args):
        self.calls += 1
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def _recover(result: ExtractionResult, client: StubExtractionClient, text: str = "Maya shared a useful idea."):
    return ensure_durable_memory(
        result,
        raw_text=text,
        llm=client,
        system_prompt="system",
        user_prompt="user",
        schema_json="{}",
    )


def test_semantic_retry_recovers_empty_extraction() -> None:
    client = StubExtractionClient(
        {
            "entry_summary": "Maya shared a useful idea.",
            "entities": [{"surface_name": "Maya", "type": "person"}],
            "memories": [{"memory_type": "observation", "text": "Maya shared a useful idea."}],
        }
    )

    result = _recover(ExtractionResult(entry_summary="Extraction failed"), client)

    assert client.calls == 1
    assert result.entry_summary == "Maya shared a useful idea."
    assert result.memories[0].text == "Maya shared a useful idea."
    assert result.entities[0].surface_name == "Maya"


def test_source_fallback_preserves_first_pass_fields_without_inventing_structure() -> None:
    client = StubExtractionClient(RuntimeError("provider unavailable"))
    first_pass = ExtractionResult(
        entities=[ExtractedEntity(surface_name="Maya", type="person")],
        action_items=[ExtractedActionItem(description="Text Maya")],
    )

    result = _recover(first_pass, client, "Maya said the quiet version should work first.")

    assert client.calls == 1
    assert result.entities == first_pass.entities
    assert result.action_items == first_pass.action_items
    assert result.memories[0].text == "User recorded: Maya said the quiet version should work first."
    assert result.memories[0].epistemic_status == "self_report"


def test_existing_memory_skips_semantic_retry() -> None:
    client = StubExtractionClient(AssertionError("retry should not run"))
    first_pass = ExtractionResult(
        memories=[ExtractedMemory(memory_type="thought", text="Attention compounds.")],
    )

    result = _recover(first_pass, client)

    assert result is first_pass
    assert client.calls == 0
