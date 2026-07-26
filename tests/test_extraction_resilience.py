from __future__ import annotations


def test_nullable_claim_status_defaults_without_dropping_extracted_items() -> None:
    from thoughtpins.llm import AttributedQuote, ExtractedMemory, SocialDynamic

    memory = ExtractedMemory(memory_type="observation", text="Maya arrived.", claim_status=None)
    dynamic = SocialDynamic(observation="Maya welcomed the group.", claim_status=None)
    quote = AttributedQuote(speaker="Maya", quote="Welcome.", claim_status=None)

    assert memory.claim_status == "active"
    assert dynamic.claim_status == "active"
    assert quote.claim_status == "active"


def test_partial_recovery_preserves_social_and_provenance_fields(monkeypatch) -> None:
    import thoughtpins.ingestion.extraction as extraction

    payload = {
        "scene_analysis": {
            "domain": "social",
            "primary_topics": ["trust"],
            "narrative_threads": ["Nora's account changed"],
            "unresolved_threads": ["Ask Eli what happened"],
        },
        "entry_summary": "Nora repeated and then withdrew a claim about Eli.",
        "entry_type": "journal_entry",
        "sensitivity_tags": ["sensitive_third_party"],
        "entities": [{"surface_name": "Nora", "type": "person"}],
        "memories": [
            {
                "memory_type": "quote",
                "text": "Nora said Eli planned to leave.",
                "attributed_to": "Nora",
                "epistemic_status": "hearsay",
                "claim_status": "retracted",
            },
            {"text": "invalid because memory_type is required"},
        ],
        "social_dynamics": [
            {
                "observation": "Nora withdrew the claim.",
                "people_involved": ["Nora", "Eli"],
                "claim_status": "retracted",
            }
        ],
        "timeline_items": [
            {
                "description": "Nora corrected herself later.",
                "relative_position": "after",
            }
        ],
        "action_items": [{"description": "Ask Eli directly", "status": "open"}],
        "expenses": [{"amount": 12.5, "merchant_or_place": "Atlas Cafe"}],
        "quotes": ["I was wrong about that."],
        "attributed_quotes": [
            {
                "speaker": "Nora",
                "quote": "I was wrong about that.",
                "is_exact": True,
                "people_discussed": ["Eli"],
                "epistemic_status": "attributed_statement",
                "claim_status": "retracted",
            }
        ],
        "open_questions": ["What actually happened?"],
    }

    class FakeClient:
        def extract_json(self, *_args):
            return payload

    monkeypatch.setattr(extraction, "get_llm_client", lambda: FakeClient())
    result = extraction.extract_from_entry("A short social scene.", "2026-07-21T18:00:00")

    assert result.scene_analysis.domain == "social"
    assert result.scene_analysis.unresolved_threads == ["Ask Eli what happened"]
    assert len(result.memories) == 1
    assert result.memories[0].claim_status == "retracted"
    assert result.social_dynamics[0].claim_status == "retracted"
    assert result.timeline_items[0].relative_position == "after"
    assert result.action_items[0].description == "Ask Eli directly"
    assert result.expenses[0].amount == 12.5
    assert result.attributed_quotes[0].speaker == "Nora"
    assert result.attributed_quotes[0].claim_status == "retracted"
    assert result.open_questions == ["What actually happened?"]


def test_paragraph_retry_merges_complete_extraction_surface() -> None:
    import thoughtpins.ingestion.extraction as extraction

    payloads = [
        {
            "scene_analysis": {
                "domain": "social",
                "primary_topics": ["friendship"],
                "narrative_threads": ["Maya's invitation"],
            },
            "entry_summary": "Maya invited the user.",
            "memories": [{"memory_type": "event", "text": "Maya invited the user."}],
            "social_dynamics": [{"observation": "Maya offered support."}],
            "timeline_items": [{"description": "Maya made the invitation."}],
            "attributed_quotes": [{"speaker": "Maya", "quote": "Come with us."}],
            "quotes": ["Come with us."],
            "open_questions": ["Who else is going?"],
        },
        {
            "scene_analysis": {
                "domain": "work",
                "primary_topics": ["career"],
                "unresolved_threads": ["Reply by Friday"],
            },
            "entry_summary": "The user needed to reply.",
            "memories": [{"memory_type": "commitment", "text": "Reply to Maya by Friday."}],
            "action_items": [{"description": "Reply to Maya", "due_at": "Friday"}],
            "expenses": [{"amount": 9.0, "merchant_or_place": "Atlas Cafe"}],
            "quotes": ["Come with us."],
            "open_questions": ["Who else is going?"],
        },
    ]

    class FakeClient:
        def __init__(self):
            self.index = 0

        def extract_json(self, *_args):
            payload = payloads[self.index]
            self.index += 1
            return payload

    result = extraction._paragraph_extract(
        FakeClient(),
        "system",
        ["First paragraph has enough content.", "Second paragraph has enough content."],
        "2026-07-21T18:00:00",
        "{}",
    )

    assert result is not None
    assert len(result.memories) == 2
    assert len(result.social_dynamics) == 1
    assert len(result.timeline_items) == 1
    assert len(result.action_items) == 1
    assert len(result.expenses) == 1
    assert len(result.attributed_quotes) == 1
    assert result.quotes == ["Come with us."]
    assert result.open_questions == ["Who else is going?"]
    assert result.scene_analysis.primary_topics == ["friendship", "career"]
    assert result.scene_analysis.unresolved_threads == ["Reply by Friday"]


def test_extract_from_entry_retries_semantically_empty_payload(monkeypatch) -> None:
    import thoughtpins.ingestion.extraction as extraction

    payloads = [
        {"entry_summary": "Extraction failed"},
        {
            "entry_summary": "Maya shared the draft at Atlas Cafe.",
            "memories": [
                {
                    "memory_type": "event",
                    "text": "Maya shared the draft at Atlas Cafe.",
                }
            ],
        },
    ]

    class FakeClient:
        def extract_json(self, *_args):
            return payloads.pop(0)

    monkeypatch.setattr(extraction, "get_llm_client", FakeClient)

    result = extraction.extract_from_entry(
        "Maya shared the draft at Atlas Cafe.",
        "2026-07-21 18:00 EDT",
    )

    assert not payloads
    assert result.entry_summary == "Maya shared the draft at Atlas Cafe."
    assert [memory.text for memory in result.memories] == ["Maya shared the draft at Atlas Cafe."]


def test_extract_from_entry_recovers_explicit_fields_after_two_empty_payloads(monkeypatch) -> None:
    import thoughtpins.ingestion.extraction as extraction

    class EmptyClient:
        def extract_json(self, *_args):
            return {"entry_summary": "Extraction failed"}

    monkeypatch.setattr(extraction, "get_llm_client", EmptyClient)
    text = "I spent $8 at Atlas Cafe. Tomorrow at 3pm, remind me to send Maya the draft."

    result = extraction.extract_from_entry(text, "2026-07-21 18:00 EDT")

    assert result.memories[0].text == f"User recorded: {text}"
    assert result.expenses[0].amount == 8
    assert result.expenses[0].merchant_or_place == "Atlas Cafe"
    assert result.action_items[0].description == "send Maya the draft"
    assert result.action_items[0].due_at == "Tomorrow at 3pm"
