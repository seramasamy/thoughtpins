"""Typed memory ontology for extraction and graph constraints.

The ontology is intentionally small. It gives the extractor domain vocabulary
and keeps graph edges queryable instead of letting the LLM invent generic
``Topic`` / ``Object`` / ``RELATES_TO`` shapes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

ENTITY_TYPES = {
    "person": "A real human being the user knows, meets, mentions, or quotes.",
    "place": "A physical location, venue, city, home, office, or merchant location.",
    "organization": "A company, school, institution, publication, group, or team.",
    "project": "A specific initiative, app, codebase, goal, research effort, or deliverable.",
    "technology": "A programming language, framework, model, database, tool, API, or platform.",
    "document": "An article, book, paper, essay, PDF, note, source, or imported reading material.",
    "idea": "A specific business idea, product idea, creative idea, or strategic hypothesis.",
    "event": "A meeting, date, trip, appointment, party, call, workout, meal, or occurrence in time.",
    "thing": "A concrete object, product, device, artifact, recipe, tool, or personal possession that is not a person, place, organization, project, document, or abstract concept.",
    "topic": "A field of study, certification, industry, subject, practice, or recurring theme.",
    "concept": "An abstract principle, value, feeling, tradeoff, framework, or philosophical concept.",
}

EDGE_TYPES = {
    "knows": "A person/user knows, is friends with, is related to, or has a personal tie with another person.",
    "works_with": "A person/user works with, collaborates with, reports to, or is professionally tied to a person/organization.",
    "works_on": "A person/user is building, studying, improving, or actively contributing to a project/topic.",
    "uses_technology": "A person/user/project uses a specific technology, model, database, API, framework, or tool.",
    "met_at": "A person/user met someone or attended something at a place or event.",
    "located_at": "An event, organization, project, or place is located at a physical place.",
    "discussed": "A person/user discussed, mentioned, quoted, or thought about a topic/project/document/idea/person.",
    "created": "A person/user/organization created, wrote, built, drafted, imported, or saved a project/document/idea.",
    "read": "A person/user read, imported, summarized, or wants to remember a document/source.",
    "associated_with": "A meaningful association that does not fit a more specific allowed edge.",
}

ENTITY_TYPE_ALIASES = {
    "company": "organization",
    "school": "organization",
    "institution": "organization",
    "team": "organization",
    "merchant": "place",
    "location": "place",
    "venue": "place",
    "source": "document",
    "article": "document",
    "book": "document",
    "paper": "document",
    "essay": "document",
    "technology": "technology",
    "tech": "technology",
    "tool": "technology",
    "framework": "technology",
    "database": "technology",
    "model": "technology",
    "object": "thing",
    "item": "thing",
    "thing": "thing",
    "product": "thing",
    "device": "thing",
    "artifact": "thing",
    "possession": "thing",
    "recipe": "thing",
    "meal": "thing",
    "app": "project",
    "codebase": "project",
    "goal": "project",
    "plan": "project",
    "certification": "topic",
    "exam": "topic",
    "subject": "topic",
    "feeling": "concept",
    "emotion": "concept",
}

RELATION_TYPE_ALIASES = {
    "friend_of": "knows",
    "parent_of": "knows",
    "child_of": "knows",
    "colleague_of": "works_with",
    "works_at": "works_with",
    "contributed_to": "works_on",
    "studying_for": "works_on",
    "preparing_for": "works_on",
    "tracking": "works_on",
    "attended": "met_at",
    "mentioned": "discussed",
    "said": "discussed",
    "quote": "discussed",
    "built": "created",
    "wrote": "created",
    "imported": "created",
    "saved": "created",
    "uses": "uses_technology",
    "runs_on": "uses_technology",
    "powered_by": "uses_technology",
    "relates_to": "associated_with",
    "unknown": "associated_with",
}

EDGE_SOURCE_TARGETS = {
    "knows": {
        ("person", "person"),
    },
    "works_with": {
        ("person", "person"),
        ("person", "organization"),
    },
    "works_on": {
        ("person", "project"),
        ("person", "topic"),
        ("person", "idea"),
        ("organization", "project"),
    },
    "uses_technology": {
        ("person", "technology"),
        ("project", "technology"),
        ("organization", "technology"),
    },
    "met_at": {
        ("person", "place"),
        ("person", "event"),
    },
    "located_at": {
        ("event", "place"),
        ("organization", "place"),
        ("project", "place"),
    },
    "discussed": {
        ("person", "person"),
        ("person", "project"),
        ("person", "technology"),
        ("person", "topic"),
        ("person", "concept"),
        ("person", "document"),
        ("person", "idea"),
        ("person", "organization"),
        ("person", "thing"),
    },
    "created": {
        ("person", "project"),
        ("person", "document"),
        ("person", "idea"),
        ("person", "topic"),
        ("person", "concept"),
        ("person", "thing"),
        ("organization", "project"),
        ("organization", "document"),
    },
    "read": {
        ("person", "document"),
    },
}


@dataclass(frozen=True)
class OntologyDecision:
    allowed: bool
    relation_type: str
    reason: str = ""


def normalize_entity_type(entity_type: str | None) -> str:
    value = (entity_type or "").strip().lower()
    if value in ENTITY_TYPES:
        return value
    return ENTITY_TYPE_ALIASES.get(value, "concept")


def normalize_relation_type(relation_type: str | None) -> str:
    value = (relation_type or "").strip().lower()
    if value in EDGE_TYPES:
        return value
    return RELATION_TYPE_ALIASES.get(value, "associated_with")


def relationship_allowed(
    relation_type: str | None,
    source_entity_type: str | None,
    target_entity_type: str | None,
) -> OntologyDecision:
    relation = normalize_relation_type(relation_type)
    source_type = normalize_entity_type(source_entity_type)
    target_type = normalize_entity_type(target_entity_type)
    if relation == "associated_with":
        return OntologyDecision(True, relation)
    allowed_pairs = EDGE_SOURCE_TARGETS.get(relation, set())
    if (source_type, target_type) in allowed_pairs:
        return OntologyDecision(True, relation)
    return OntologyDecision(False, relation, f"{relation} cannot connect {source_type} -> {target_type}")


def ontology_prompt_block() -> str:
    entities = "\n".join(f"- {name}: {description}" for name, description in ENTITY_TYPES.items())
    edges = "\n".join(f"- {name}: {description}" for name, description in EDGE_TYPES.items())
    constraints = "\n".join(
        f"- {edge}: " + ", ".join(f"{source}->{target}" for source, target in sorted(pairs))
        for edge, pairs in EDGE_SOURCE_TARGETS.items()
    )
    return f"""## MEMORY ONTOLOGY
Use this ontology as the schema for the user's memory graph. Do not invent new entity or relationship types.

ENTITY TYPES:
{entities}

EDGE TYPES:
{edges}

SOURCE/TARGET CONSTRAINTS:
{constraints}
- associated_with: fallback only when no more specific edge applies.

If a relationship does not satisfy a constraint, prefer a valid edge type or omit it. Keep rich details in memories."""


def ontology_schema_fragment() -> dict[str, object]:
    return {
        "allowed_entity_types": list(ENTITY_TYPES),
        "allowed_relationship_types": list(EDGE_TYPES),
        "edge_source_target_constraints": {
            edge: [{"source": source, "target": target} for source, target in sorted(pairs)]
            for edge, pairs in EDGE_SOURCE_TARGETS.items()
        },
    }


def summarize_allowed_types(values: Iterable[str]) -> str:
    return " | ".join(values)
