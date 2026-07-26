"""Human-readable fictional content for local product demonstrations."""

from __future__ import annotations

from dataclasses import dataclass

MARKER = "TP_DEMO_CORPUS"


@dataclass(frozen=True)
class JournalFixture:
    key: str
    days_ago: int
    local_time: str
    text: str
    importance: int
    entity_keys: tuple[str, ...] = ()
    memory_type: str = "observation"
    predicate: str = "records"
    is_private: bool = False
    action_count: int = 0
    decision_count: int = 0
    event_count: int = 0
    relationship_count: int = 0


JOURNAL_FIXTURES = (
    JournalFixture(
        key="weekly_intention",
        days_ago=7,
        local_time="08:10",
        text=(
            "I want this week to feel less reactive. I am protecting the first hour of each morning for quiet "
            "work before opening messages, then taking a short walk after lunch so the day has a clear middle."
        ),
        importance=4,
        entity_keys=("deliberate_pace",),
        memory_type="decision",
        predicate="committed_to",
        decision_count=1,
    ),
    JournalFixture(
        key="coffee_chat",
        days_ago=6,
        local_time="10:35",
        text=(
            "Coffee with Maya Arlen at Atlas Cafe felt unusually useful. She suggested testing Quiet Systems with "
            "five people before adding another feature. The tiny blue ceramic swallow above the register made the "
            "place easy to remember. I promised to send her the revised prototype on Tuesday."
        ),
        importance=5,
        entity_keys=("maya", "atlas_cafe", "ceramic_swallow", "quiet_systems"),
        memory_type="relationship_update",
        predicate="discussed_at",
        action_count=1,
        decision_count=1,
        event_count=1,
        relationship_count=2,
    ),
    JournalFixture(
        key="recipe_note",
        days_ago=5,
        local_time="19:20",
        text=(
            "The lemon-miso pasta finally worked: one tablespoon of white miso, zest from half a lemon, a spoonful "
            "of pasta water, and black pepper. Add the lemon juice after the pan is off the heat so it stays bright."
        ),
        importance=2,
        entity_keys=("lemon_miso_pasta",),
        memory_type="fact",
        predicate="recipe_for",
    ),
    JournalFixture(
        key="reading_reflection",
        days_ago=4,
        local_time="21:05",
        text=(
            "Reading Sherlock Holmes made me notice how often a small physical detail becomes useful only after a "
            "second fact gives it context. That feels like the right model for memory retrieval: preserve the clue, "
            "its source, and the bridge that later makes it relevant."
        ),
        importance=3,
        entity_keys=("sherlock_thread", "evidence_bridges"),
        memory_type="thought",
        predicate="connected_to",
    ),
    JournalFixture(
        key="product_decision",
        days_ago=3,
        local_time="14:45",
        text=(
            "Decision for Quiet Systems: keep conversation as the front door. Cards, timelines, sources, and recaps "
            "should help when needed, but the product should never make someone learn database vocabulary before "
            "they can write down a thought."
        ),
        importance=5,
        entity_keys=("quiet_systems", "deliberate_pace"),
        memory_type="decision",
        predicate="guides",
        decision_count=1,
    ),
    JournalFixture(
        key="private_reflection",
        days_ago=2,
        local_time="22:15",
        text=(
            "I felt nervous before showing the prototype, even though the feedback was kind. The useful part was "
            "noticing that the anxiety eased once I stopped trying to explain every feature at once."
        ),
        importance=4,
        entity_keys=(),
        memory_type="reflection",
        predicate="felt",
        is_private=True,
    ),
    JournalFixture(
        key="river_walk",
        days_ago=1,
        local_time="17:40",
        text=(
            "Walked the Riverfront Loop just before sunset and left my phone in my pocket. I kept returning to "
            "Maya's advice about smaller tests. Tomorrow's priority is to send the prototype, then leave the rest "
            "of the afternoon unscheduled."
        ),
        importance=4,
        entity_keys=("riverfront_loop", "maya", "quiet_systems"),
        memory_type="future_plan",
        predicate="planned_after",
        action_count=1,
        event_count=1,
        relationship_count=1,
    ),
)


BOOK_TEXT = (
    "Arthur Conan Doyle's early Sherlock Holmes stories repeatedly connect observation with delayed interpretation. "
    "Sherlock Holmes and Dr. Watson encounter clues whose significance depends on relationships between people, "
    "places, and earlier events. A Study in Scarlet establishes Watson's first impressions and Holmes's method. "
    "The Sign of the Four introduces Mary Morstan and the recurring pearl clue. Irene Adler belongs to A Scandal in "
    "Bohemia. These are literary source facts, not people or events from the reader's own life."
)

SATIRE_TEXT = (
    "Jonathan Swift's A Modest Proposal uses an intentionally detached economic voice and moral shock to expose "
    "indifference toward poverty. Its useful reading concepts are satire, unreliable surface tone, policy rhetoric, "
    "and the distance between a speaker's literal proposal and an author's moral argument."
)

OBSIDIAN_TEXT = (
    "An Obsidian-compatible vault is a folder of ordinary Markdown notes and attachments. Thought Pins exports "
    "journal dates, people, places, concepts, source notes, properties, and internal links in a human-readable form. "
    "The application database remains the live transactional system; the vault is the portable archive."
)


ENTITY_SPECS = {
    "maya": ("person", "Maya Arlen", ("Maya",), "Friend and product-thinking collaborator."),
    "atlas_cafe": ("place", "Atlas Cafe", ("Atlas",), "Cafe remembered by a blue ceramic swallow above the register."),
    "ceramic_swallow": ("thing", "Blue Ceramic Swallow", ("ceramic swallow",), "Small visual anchor at Atlas Cafe."),
    "quiet_systems": ("project", "Quiet Systems", ("the prototype",), "A fictional calm-software prototype."),
    "deliberate_pace": (
        "concept",
        "Deliberate Pace",
        ("less reactive",),
        "Protecting attention through intentional pacing.",
    ),
    "lemon_miso_pasta": ("thing", "Lemon-Miso Pasta", ("lemon miso pasta",), "A saved recipe and cooking detail."),
    "sherlock_thread": (
        "concept",
        "Sherlock Holmes Reading Thread",
        ("Sherlock Holmes",),
        "Reading notes about observation and evidence.",
    ),
    "evidence_bridges": (
        "concept",
        "Evidence Bridges",
        ("bridge fact",),
        "Facts that connect otherwise distant memories.",
    ),
    "riverfront_loop": ("place", "Riverfront Loop", ("river walk",), "A recurring walking route."),
}

ENTITY_NAMES = tuple(spec[1] for spec in ENTITY_SPECS.values())

SOURCE_TITLES = (
    "Observation and Memory in Sherlock Holmes",
    "Satire and Moral Distance",
    "Portable Notes and Obsidian",
)

CHAT_USER_TEXT = "What was the small detail I noticed when Maya and I talked about the prototype?"
CHAT_ASSISTANT_TEXT = (
    "At Atlas Cafe, you noticed the tiny blue ceramic swallow above the register. Maya suggested testing Quiet "
    "Systems with five people before adding another feature, and you promised to send her the revised prototype."
)
