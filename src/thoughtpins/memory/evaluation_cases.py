"""Human-labeled queries for the deterministic memory benchmark fixture."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryEvalDefinition:
    name: str
    query: str
    expected_terms: tuple[str, ...]
    relevance_markers: tuple[str, ...]
    use_context_package: bool = False


def memory_eval_definitions() -> tuple[MemoryEvalDefinition, ...]:
    """Return stable judgments independent of the ranking implementation."""
    return (
        MemoryEvalDefinition(
            "obscure_journal_recall",
            "what did Priya say mattered more than animation polish?",
            ("backup restore",),
            ("At Marlow Coffee, Priya",),
        ),
        MemoryEvalDefinition(
            "document_obscure_recall",
            "what was the violet keystone detail?",
            ("violet keystone", "Old Recall Paper"),
            ("The old paper mentioned",),
        ),
        MemoryEvalDefinition(
            "graph_entity_bridge",
            "what technology does Project Atlas use?",
            ("PostgreSQL",),
            ("Alice manages Project Atlas",),
        ),
        MemoryEvalDefinition(
            "multi_hop_bridge",
            "was Alice's project affected by Tuesday's outage?",
            ("Project Atlas", "PostgreSQL", "Tuesday"),
            ("Alice manages Project Atlas", "cluster went down Tuesday"),
        ),
        MemoryEvalDefinition(
            "context_composition",
            "what should I remember about Priya and the recall paper?",
            ("Priya", "violet keystone"),
            ("At Marlow Coffee, Priya", "The old paper mentioned"),
            use_context_package=True,
        ),
        MemoryEvalDefinition(
            "quick_bar_note_recall",
            "what did Maya say about the rye sour at Lumen?",
            ("Maya", "bitters", "orange peel"),
            ("Quick bar note",),
        ),
        MemoryEvalDefinition(
            "date_night_recall",
            "what was the no phones dinner rule connected to?",
            ("Koyo Ramen", "Willow Park", "no-phones-at-dinner"),
            ("Date night note",),
        ),
        MemoryEvalDefinition(
            "networking_event_recall",
            "who from TerraLoop cared about compliance tooling?",
            ("Daniel", "TerraLoop", "compliance tooling"),
            ("Networking event note",),
        ),
        MemoryEvalDefinition(
            "recipe_recall",
            "what goes in the turmeric lentil stew?",
            ("chickpeas", "cumin", "yogurt"),
            ("Recipe note",),
        ),
        MemoryEvalDefinition(
            "business_idea_recall",
            "what should Northstar Memory prioritize before social features?",
            ("local-first", "recall diagnostics"),
            ("Business idea",),
        ),
        MemoryEvalDefinition(
            "spiritual_philosophy_recall",
            "what did I write about prayer and attention?",
            ("listening", "budget", "mood"),
            ("Spiritual thought",),
        ),
        MemoryEvalDefinition(
            "book_series_recall",
            "what ritual in Sable Notebook Chapter Seven remembered the twins?",
            ("amber compass", "river city twins"),
            ("The book note said Chapter Seven",),
        ),
        MemoryEvalDefinition(
            "broad_context_composition",
            "connect Daniel, Northstar Memory, and the Sable Notebook note",
            ("Daniel", "Northstar Memory", "amber compass"),
            ("Networking event note", "Business idea", "The book note said Chapter Seven"),
        ),
        MemoryEvalDefinition(
            "public_domain_novel_recall",
            "what was the wall clue in A Study in Scarlet?",
            ("A Study in Scarlet", "RACHE"),
            ("Public-domain novel note",),
        ),
        MemoryEvalDefinition(
            "public_domain_philosophy_recall",
            "what did the Meditations note say about ten thousand years?",
            ("Meditations", "ten thousand years"),
            ("Public-domain philosophy note",),
        ),
        MemoryEvalDefinition(
            "attributed_rumor_and_retraction",
            "what rumor did Nora share about Eli, where did she share it, and what happened later?",
            ("Nora", "Eli", "Halcyon House", "retracted", "denied"),
            ("At Halcyon House, Nora", "Two days later Nora retracted"),
        ),
        MemoryEvalDefinition(
            "school_social_cause",
            "why did Sam skip rehearsal and who explained it?",
            ("Sam", "Ava", "mocked", "audition draft"),
            ("At Westbridge Library, Ava",),
        ),
        MemoryEvalDefinition(
            "creative_decision_cause",
            "why did Celia say the North Gallery series should be smaller?",
            ("Celia", "North Gallery", "blue canvases"),
            ("In Celia's studio",),
        ),
    )
