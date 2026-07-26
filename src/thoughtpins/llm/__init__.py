"""Pydantic v2 schemas for LLM structured extraction."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from thoughtpins.memory.ontology import normalize_entity_type, normalize_relation_type


def _claim_status_or_default(value: Any) -> str:
    """Keep otherwise valid extraction items when a provider emits JSON null."""
    if value is None:
        return "active"
    normalized = str(value).strip()
    return normalized or "active"


class SceneAnalysis(BaseModel):
    domain: str = "mixed"
    primary_topics: list[str] = Field(default_factory=list)
    emotional_tone: str = "neutral"
    social_dynamics_summary: str = ""
    entry_type: str = "narrative"
    narrative_threads: list[str] = Field(default_factory=list)
    unresolved_threads: list[str] = Field(default_factory=list)


class EntityAttribute(BaseModel):
    key: str
    value: Any = ""  # Accept any type, coerce to string
    confidence: str = "observed_by_user"
    sensitivity: str = "personal"
    temporal_scope: str = "current_as_of_entry"

    @field_validator("value", mode="before")
    @classmethod
    def coerce_value_to_str(cls, v):
        if v is None:
            return ""
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return str(v)
        return str(v) if not isinstance(v, str) else v


class ExtractedEntity(BaseModel):
    surface_name: str
    canonical_guess: Optional[str] = None
    type: str = "person"
    aliases: list[str] = Field(default_factory=list)
    attributes: list[EntityAttribute] = Field(default_factory=list)

    @model_validator(mode="after")
    def fill_canonical(self):
        if self.canonical_guess is None:
            self.canonical_guess = self.surface_name
        self.type = normalize_entity_type(self.type)
        return self


class ExtractedEvent(BaseModel):
    name: str
    event_type: str = "other"
    date_inferred_from_message: bool = True
    place: Optional[str] = None
    participants: list[str] = Field(default_factory=list)
    summary: str = ""
    purpose: str = ""
    outcome: str = ""
    social_stakes: str = "low"
    sensitivity: str = "personal"


class ExtractedMemory(BaseModel):
    memory_type: str
    text: str
    subject: Optional[str] = None
    predicate: Optional[str] = None
    object: Optional[str] = None
    confidence: str = "observed_by_user"
    sensitivity: str = "personal"
    relative_date: Optional[str] = None
    attributed_to: Optional[str] = None
    people_involved: list[str] = Field(default_factory=list)
    place: Optional[str] = None
    epistemic_status: str = "direct_observation"
    claim_status: str = "active"
    motivation: Optional[str] = None
    consequence: Optional[str] = None
    open_loop: bool = False
    social_stakes: str = "low"

    _normalize_claim_status = field_validator("claim_status", mode="before")(_claim_status_or_default)


class ExtractedRelationship(BaseModel):
    source: str
    relation_type: str
    target: str
    confidence: str = "observed_by_user"
    sensitivity: str = "personal"

    @model_validator(mode="after")
    def normalize_relation(self):
        self.relation_type = normalize_relation_type(self.relation_type)
        return self


class SocialDynamic(BaseModel):
    observation: str = ""
    people_involved: list[str] = Field(default_factory=list)
    dynamic_type: str = "other"
    description: str = ""
    significance: str = ""
    attributed_to: Optional[str] = None
    confidence: str = "user_reported"
    claim_status: str = "active"
    social_stakes: str = "medium"
    open_loop: bool = False

    _normalize_claim_status = field_validator("claim_status", mode="before")(_claim_status_or_default)


class AttributedQuote(BaseModel):
    """A statement with enough provenance to survive later retrieval."""

    speaker: str
    quote: str
    is_exact: bool = False
    context: str = ""
    people_discussed: list[str] = Field(default_factory=list)
    confidence: str = "user_reported"
    epistemic_status: str = "attributed_statement"
    claim_status: str = "active"
    social_stakes: str = "low"

    _normalize_claim_status = field_validator("claim_status", mode="before")(_claim_status_or_default)


class TimelineItem(BaseModel):
    description: str = ""
    relative_position: str = "during"
    related_to: str = ""
    temporal_expression: str = ""


class ExtractedActionItem(BaseModel):
    description: str
    due_at: Optional[str] = None
    owner: Optional[str] = None
    status: str = "open"
    sensitivity: str = "personal"


class ExtractedExpense(BaseModel):
    amount: Optional[float] = None
    currency: str = "USD"
    merchant_or_place: Optional[str] = None
    reason: Optional[str] = None
    category: Optional[str] = None
    confidence: str = "observed_by_user"


class ExtractionResult(BaseModel):
    """The complete structured output the LLM must produce."""

    scene_analysis: SceneAnalysis = Field(default_factory=SceneAnalysis)
    entry_summary: str = ""
    entry_type: str = "journal_entry"
    sensitivity_tags: list[str] = Field(default_factory=list)
    entities: list[ExtractedEntity] = Field(default_factory=list)
    events: list[ExtractedEvent] = Field(default_factory=list)
    memories: list[ExtractedMemory] = Field(default_factory=list)
    relationships: list[ExtractedRelationship] = Field(default_factory=list)
    social_dynamics: list[SocialDynamic] = Field(default_factory=list)
    timeline_items: list[TimelineItem] = Field(default_factory=list)
    action_items: list[ExtractedActionItem] = Field(default_factory=list)
    expenses: list[ExtractedExpense] = Field(default_factory=list)
    quotes: list[str] = Field(default_factory=list)
    attributed_quotes: list[AttributedQuote] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
