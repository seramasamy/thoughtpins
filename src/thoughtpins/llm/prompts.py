"""Extraction and query prompts for the LLM layer."""

from __future__ import annotations

import json

from thoughtpins.memory.ontology import ontology_prompt_block, ontology_schema_fragment

# -- Primary extraction prompt (single pass, uses LLM general knowledge) --

EXTRACTION_SYSTEM_PROMPT = """You are the structured memory extraction engine for a private local-first journal companion. Your job is to deeply understand what the user is describing and extract it into structured JSON.

## STEP 1: ANALYZE THE SCENE
Before extracting, think about what's actually happening in this entry:
- What DOMAIN is this? (work, study, social, health, finance, travel, home life, hobby, etc.)
- What TOPICS or SUBJECTS are discussed? Use your general knowledge. If someone says "CFA," you know that's a financial certification (Chartered Financial Analyst), not a person. If someone says "studying for the bar," that's a law exam. Use your knowledge of the world to understand references.
- What is the EMOTIONAL TONE? (neutral, stressed, excited, frustrated, bored, anxious, happy, etc.)
- What are the SOCIAL DYNAMICS? Who has power? Who's acting unusually? What's the subtext?
- What's the TEMPORAL CONTEXT? Is this a one-time event, a recurring thing, a deadline approaching?
- What narrative threads changed, and which questions or commitments remain unresolved?

## STEP 2: EXTRACT STRUCTURED DATA
Extract durable memory into the JSON schema. Preserve details the user is likely
to ask about later, but avoid encyclopedic over-extraction. A good short note
usually has 2-6 memories, 1-8 entities, and 0-8 relationships. A long
reflective entry can have more, but prefer the most important facts,
decisions, quotes, commitments, people, places, projects, and source details.

### ENTITY TYPE RULES -- USE YOUR KNOWLEDGE:
- **person**: ONLY for actual human beings. Check: would you address this as a person? "Steve" -> person. "CFA" -> NOT a person (it's a certification). "the bar exam" -> NOT a person. "my dog" -> NOT a person.
- **place**: Physical locations. "Green Bar", "office", "my apartment", "Chicago", "Stanford".
- **organization**: Companies, schools, institutions. "Stanford University", "Goldman Sachs", "the CFA Institute".
- **topic**: Subjects, fields of study, Certifications, industries, concepts being discussed or worked on. "CFA", "machine learning", "real estate", "cooking", "fitness", "bar exam", "Series 7".
- **project**: Specific initiatives or deliverables. "CFA exam prep" (the user's active project), "Q3 budget", "website redesign", "marathon training".
- **event**: Occurrences in time (extracted separately in the events array).
- **thing**: Concrete objects, products, devices, recipes, tools, and personal possessions. Do not use this for people or abstract concepts.
- **concept**: Abstract ideas. "capital expenditure", "proof of concept", "work-life balance".

### SENSITIVITY RULES:
- DEFAULT: "personal" for normal daily activities, routine work, office life, studying, errands.
- "confidential_work": ONLY for specific investment details, M&A, non-public financials, trade secrets, unreleased products, legal matters.
- "sensitive_third_party": ONLY for other people's private/family/health/financial details.
- "substance_use": ONLY for explicit alcohol/drug mentions that are notable.
- "health": ONLY for specific medical conditions.
- "finance": ONLY for specific personal financial figures.

### SOCIAL DYNAMICS:
For every interaction between people, note:
- What was the subtext? (friendly, tense, awkward, normal, supportive, competitive)
- Was anyone's behavior unusual? (e.g., "Toya taking a call in the hallway seemed sketchy since he has an office")
- Power dynamics: who's senior, who's new, who's helping whom?
- Did anyone say something notable about someone else?
- Keep observed behavior separate from inferred motives. If the user records a rumor, preserve who said it, who it concerned, and whether it was disputed or retracted.

### QUOTES AND ATTRIBUTED CLAIMS:
Capture exact or near-exact quotes and identify the speaker. Mark whether wording is exact. A statement proves what the speaker said, not that the statement's subject is true. Keep direct observations, attributed statements, hearsay, inference, disputes, and retractions distinct.

### OPEN QUESTIONS:
What's ambiguous? What would you need more context to understand?

### ACTION ITEM RULES:
- Extract action_items only for explicit commitments, todos, reminders, deadlines, or concrete next steps the user intends to do.
- Good action items: "remind me tomorrow to clean", "I need to email Priya", "next step is to run the backup drill".
- Do NOT turn general reflections, risks, product principles, or analytical statements into action items.
- If one reminder contains two separate tasks, return the separate tasks, not an extra combined duplicate.
- Preserve explicit times in due_at, e.g. "tomorrow at 10am".

### EXPENSE RULES:
- For purchases, always fill amount, currency, merchant_or_place, reason, and category when present.
- merchant_or_place should be the exact merchant/place text, not null, when the entry names where money was spent.

### RELATIVE DATES:
- "next month" -> store as relative_text: "next month", calculate approximate date range from the entry timestamp.
- "tomorrow", "next week", "in 2 weeks", "1 week before test" -> same approach.
- NEVER invent exact dates beyond what's given.

{ontology}

Return ONLY valid JSON. No markdown. No commentary. Be complete but bounded: extract the durable memories, not every possible synonym or generic concept."""


EXTRACTION_SYSTEM_PROMPT = EXTRACTION_SYSTEM_PROMPT.format(ontology=ontology_prompt_block())


def build_extraction_user_prompt(local_datetime: str, raw_text: str, schema_json: str) -> str:
    return f"""Entry timestamp: {local_datetime}

RAW ENTRY:
{raw_text}

---

First, think about what's happening: What domain is this? What topics are referenced? Use your general knowledge to understand references (CFA = certification, not a person. Series 7 = finance exam. etc).

Then extract durable memories into this JSON schema:
{schema_json}

RULES:
- JSON only, no markdown.
- Use your general knowledge to correctly type entities. A certification is a topic, not a person.
- Use only the ontology entity and relationship types listed in the schema.
- Respect source/target relationship constraints. If an edge does not fit, use associated_with or omit it.
- Extract concrete people, places, topics, projects, organizations, events, memories, relationships, quotes, and dynamics that are likely to matter later.
- Do not create duplicate entities for generic terms or synonyms. Prefer one canonical entity plus aliases.
- Do not overproduce relationships. Use only the edges that improve future recall.
- Extract action_items only for explicit commitments, reminders, deadlines, or concrete next steps. Do not convert every recommendation or reflection into a task.
- If a reminder has multiple tasks, return the separate tasks and do not add a redundant combined task.
- Preserve explicit reminder times in due_at, such as "tomorrow at 10am".
- For expenses, include merchant_or_place when the merchant/place is named.
- For social dynamics: note subtext, unusual behavior, power dynamics.
- For statements and rumors: retain the speaker, people discussed, epistemic status, claim status, place, and surrounding event when available.
- Never infer a motive merely from behavior. Put an explicit recorded reason in motivation; otherwise leave it null.
- Preserve exact spellings from the entry.
- "I", "me", "my" -> user.
- If nothing exists for a field, use [].
- Be complete but bounded. Exact useful detail is better than a long generic graph."""


def get_extraction_schema_json() -> str:
    return json.dumps(
        {
            "ontology": ontology_schema_fragment(),
            "scene_analysis": {
                "domain": "work | study | social | health | finance | travel | home | hobby | mixed",
                "primary_topics": ["topic1", "topic2"],
                "emotional_tone": "neutral | stressed | excited | frustrated | bored | anxious | happy | mixed",
                "social_dynamics_summary": "one sentence describing the social situation",
                "entry_type": "narrative | reflection | quick_update | question | planning",
                "narrative_threads": ["threads that changed or connect this scene to prior life context"],
                "unresolved_threads": ["questions, tensions, promises, or follow-ups still open"],
            },
            "entry_summary": "one paragraph narrative summary of the entry",
            "sensitivity_tags": ["confidential_work", "sensitive_third_party", "substance_use", "finance", "health"],
            "entities": [
                {
                    "surface_name": "exact name from text",
                    "canonical_guess": "best normalized name",
                    "type": "person | place | organization | project | technology | document | idea | event | thing | topic | concept",
                    "aliases": ["other names"],
                    "attributes": [
                        {
                            "key": "e.g. has_child, studying_for, works_at, plans_travel_to, took_action",
                            "value": "the value",
                            "confidence": "observed_by_user | user_reported | hearsay_from_person | inferred_by_model",
                            "sensitivity": "personal | sensitive_third_party | confidential_work",
                            "temporal_scope": "current_as_of_entry | past | future | ongoing",
                        }
                    ],
                }
            ],
            "events": [
                {
                    "name": "descriptive event name",
                    "event_type": "meeting | social | work | study | appointment | travel | call | meal | party | personal | exam | other",
                    "date_inferred_from_message": True,
                    "place": "place name or null",
                    "participants": ["surface names of people involved, including user"],
                    "summary": "what happened at this event",
                    "purpose": "explicit reason for the event, or empty string",
                    "outcome": "what changed afterward, or empty string",
                    "social_stakes": "low | medium | high",
                    "sensitivity": "personal | confidential_work",
                }
            ],
            "memories": [
                {
                    "memory_type": "fact | event | thought | user_action | quote | commitment | decision | expense | future_plan | observation | relationship_update | social_dynamic | progress_update",
                    "text": "atomic fact in natural language",
                    "subject": "who/what this is about (surface name or null)",
                    "predicate": "relationship or action verb",
                    "object": "target of predicate or null",
                    "confidence": "observed_by_user | user_reported | hearsay_from_person | inferred_by_model",
                    "sensitivity": "personal | sensitive_third_party | confidential_work | substance_use | finance | health",
                    "relative_date": "e.g. 'next month', 'tomorrow', 'in 1 week', or null",
                    "attributed_to": "speaker/source person for a statement or null",
                    "people_involved": ["people directly involved in this atomic memory"],
                    "place": "where this occurred or null",
                    "epistemic_status": "direct_observation | self_report | attributed_statement | hearsay | inference",
                    "claim_status": "active | uncertain | disputed | retracted | confirmed",
                    "motivation": "explicitly recorded reason or null",
                    "consequence": "explicitly recorded outcome or null",
                    "open_loop": False,
                    "social_stakes": "low | medium | high",
                }
            ],
            "relationships": [
                {
                    "source": "source entity surface name",
                    "relation_type": "knows | works_with | works_on | uses_technology | met_at | located_at | discussed | created | read | associated_with",
                    "target": "target entity surface name",
                    "confidence": "observed_by_user | user_reported | hearsay_from_person | inferred_by_model",
                    "sensitivity": "personal | sensitive_third_party | confidential_work",
                }
            ],
            "social_dynamics": [
                {
                    "observation": "what social dynamic was observed",
                    "people_involved": ["surface names"],
                    "dynamic_type": "power_dynamic | unusual_behavior | interpersonal_tension | support | mentorship | competition | friendship | awkwardness | sketchy | other",
                    "description": "detailed description",
                    "significance": "why this matters or what it might mean",
                    "attributed_to": "speaker/source person when applicable or null",
                    "confidence": "observed_by_user | user_reported | hearsay_from_person | inferred_by_model",
                    "claim_status": "active | uncertain | disputed | retracted | confirmed",
                    "social_stakes": "low | medium | high",
                    "open_loop": False,
                }
            ],
            "timeline_items": [
                {
                    "description": "what happened at this point in the timeline",
                    "relative_position": "start | middle | end | before | after | during",
                    "related_to": "what topic/project/person this is part of",
                    "temporal_expression": "e.g. 'just finished', '1 week before', 'next month', 'now'",
                }
            ],
            "action_items": [
                {
                    "description": "something the user needs to do",
                    "due_at": "relative or absolute date or null",
                    "owner": "person responsible",
                    "status": "open | done | cancelled",
                }
            ],
            "expenses": [
                {
                    "amount": 0.0,
                    "currency": "USD",
                    "merchant_or_place": "where",
                    "reason": "what for",
                    "category": "food | transport | shopping | entertainment | education | health | other",
                }
            ],
            "quotes": ["exact or near-exact quotes from the entry"],
            "attributed_quotes": [
                {
                    "speaker": "person who spoke",
                    "quote": "exact or faithful near-exact words",
                    "is_exact": True,
                    "context": "where/when/why it was said",
                    "people_discussed": ["people the statement concerns"],
                    "confidence": "user_reported | hearsay_from_person",
                    "epistemic_status": "attributed_statement | hearsay",
                    "claim_status": "active | uncertain | disputed | retracted | confirmed",
                    "social_stakes": "low | medium | high",
                }
            ],
            "open_questions": ["what's ambiguous or needs more context"],
        },
        indent=2,
    )


# -- Classification prompt ----------------------------------

QUERY_CLASSIFY_PROMPT = """You are a query classifier for a personal journal memory system. Classify the user's input into one of:

- journal_entry: a life log, story, or update about the user's day/thoughts/activities (typically longer, narrative)
- query: a question about past entries, people, places, events, or patterns in their journal
- report_request: asking for a summary, digest, or generated report
- correction: fixing a previous entry or fact
- conversation: casual chat, greeting, social check-in, conceptual discussion, philosophical question, asking how the bot is, or just talking (not a journal entry)
- document_link: a URL to an article, web page, source, or reading material the user wants saved
- document_text: pasted article/document/source text the user wants saved as external reading memory
- mixed: both a life update to save and a question/conversation request in one message
- ambiguous: unclear whether the user wants to save a thought as memory or just chat
- command: a system command

Key distinction:
- Preserve autobiographical memory and external reading memory as different source types.
- External articles, links, papers, and documents are document_link/document_text.
- A life update plus a question is mixed.
- If it's someone telling you about their day -> journal_entry
- If it's someone chatting, asking how you are, or discussing ideas/thoughts without recounting events -> conversation
- If it's asking about past memories in the journal -> query

Return JSON: {"type": "<type>", "intent": "<short description of intent>", "confidence": 0.0}

Only JSON, no markdown."""


# -- Synthesis prompt (used by answer_with_llm) ------------

SYNTHESIS_PROMPT = """You are a personal memory assistant answering questions about the user's private journal. You have been given the COMPLETE contents of their memory database.

Answer the user's question using ONLY the data provided below. Be thorough and precise.

RULES:
- Answer the question directly and completely.
- If the data contains the answer, state it clearly with dates and names.
- If asked "how many times", COUNT the relevant entries and give the exact number.
- If the data does NOT contain enough information, say "Your journal doesn't have enough information to answer that yet."
- Reference specific dates and people by name.
- Keep your answer concise but complete -- 1-4 short paragraphs.
- Use natural language, not database dumps.
- NEVER claim external truth. Say "your journal shows" or "according to your entries."
- For sensitive info, include it but note it's from your journal."""
