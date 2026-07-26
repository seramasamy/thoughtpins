# Social-Episodic Relevance

## Objective

Thought Pins should retrieve the evidence a person needs to understand a
memory, not merely the chunks with the nearest embedding. For social memories,
that usually means preserving who was involved, what each person said, where
and when the scene occurred, why it mattered, what followed, and what remains
unresolved.

This is a personal retrieval system, not an engagement feed. It does not rank
people by worth or optimize for outrage. Social stakes and explicit importance
can break close relevance ties, but neither can manufacture truth or displace a
substantially better query match.

## Serving Pipeline

1. Candidate generation unions exact phrase, BM25-style lexical, embedding,
   document, temporal SQL, and graph evidence under the tenant scope.
2. Reciprocal-rank fusion and independent-channel consensus calibrate candidate
   relevance without comparing provider-specific raw scores directly.
3. `social_relevance.py` analyzes explicitly requested facets: people,
   statement, place, time, cause, outcome, relationship, uncertainty, and open
   loop.
4. Each candidate receives bounded, inspectable signals for facet coverage,
   attribution quality, scene completeness, narrative salience, epistemic fit,
   and factualization risk.
5. Stars and inferred salience remain bounded. During a social query, the star
   prior is gated by requested-facet coverage and person-identity match, so a
   highly rated but unrelated memory cannot outrank the requested scene.
6. MMR penalizes textual redundancy and repeated representations of one source
   scene when the candidate pool contains distinct channels, duplicate source
   views, or different requested facets. Rare-query-aspect and narrative
   coverage repair remain active even when MMR itself is unnecessary.
7. `evidence_plan.py` emits a compact internal plan with dates, speakers,
   people, places, provenance, and epistemic status. The plan is wrapped as
   untrusted memory evidence before synthesis.
8. The synthesis contract preserves attribution, conflicting accounts,
   corrections, retractions, source-versus-lived-memory boundaries, and
   missing evidence.

Structured extraction requests standard JSON-object mode, then degrades to a
plain compatible call if an endpoint rejects that option. Malformed output is
repaired locally through a maintained parser before Pydantic validation;
partial recovery and paragraph retries retain all provenance-bearing fields.

## Claim Model

Extraction records an epistemic status (`direct_observation`, `self_report`,
`attributed_statement`, `hearsay`, or `inference`) independently from claim
lifecycle (`active`, `uncertain`, `disputed`, `retracted`, or `confirmed`).
Attributed quotes retain speaker, exactness, surrounding context, people
discussed, and social stakes. A statement is evidence that the speaker made the
statement; it is not automatically evidence that the statement's subject is
true.

Corrections and retractions control current answers. Historical accounts remain
available when the history itself is relevant. An uncertain candidate without
a speaker is penalized rather than silently presented as fact.

## Salience v4

Entry salience adds attributed statements, explicit causal links, unresolved
threads, and high-stakes social dynamics to the prior durability model. Entity
salience still emphasizes agency, structural role, independent recurrence,
graph breadth, source diversity, and temporal persistence. All feature weights
are named, normalized, versioned, persisted, and bounded.

## Evaluation

The deterministic integration fixture contains 18 checks, including 17 ranked
queries. Current results are 1.000 for Recall@10, nDCG@10, mean reciprocal rank,
MAP@10, evidence coverage, and worst-case nDCG@10.

The public-domain harness uses the official Project Gutenberg offline catalog
instead of crawling catalog pages. On 2026-07-21 its final replay evaluated 300
item-header-validated books from 306 attempts. Of those, 182 passages were
first-person dominant. Results were 1.000 Recall@1, Recall@5, Recall@10, MRR,
and attribution retention. Text caches live only in ignored `.tmp/` storage;
product memory and user vaults are untouched.

The contemporary benchmark generates adversarial, original scenes across 16
settings: high school, prep school, coastal social life, college, finance,
consulting, startups, artists, writers, music, nightlife, networking, family,
dating, travel, and community work. It deliberately includes vague five-star
decoys, same-person and same-place decoys, unattributed rumors, causes, and
outcomes. At 5,000 cases it reports 1.000 Recall@1 and Recall@3, 1.000 requested-
facet coverage, 1.000 attribution retention, zero top-ranked orphan uncertain
claims, and deterministic replay.

Independent external evaluation uses pinned, license-checked LongMemEval and
LitBank snapshots. On the 46-question LongMemEval holdout, the production
policy improved a same-candidate BM25 baseline from 0.8478 to 0.8696 Recall@1,
from 0.9065 to 0.9174 MRR, and from 0.9000 to 0.9049 nDCG@10 while retaining
1.000 Recall@5. On LitBank holdout annotations, all 25 speaker queries and all
16 minor-speaker queries reached 1.000 Recall@1 and MRR. Dataset governance,
split discipline, and limitations are recorded in
`EXTERNAL_MEMORY_BENCHMARKS.md`.

A disposable live workflow also passed 15/15 checks on 2026-07-21. It processed
six short and long entries into 38 memories and preserved speaker attribution,
a later retraction, non-orphaned hearsay, social places, causal metadata,
reminders, an expense, and memory-backed conversational answers. The workflow
redirects its database, vector path, vault, reports, backups, and conversation
cache into a unique scratch root and removes them afterward.

Run the checks with:

```powershell
python scripts/evaluate_memory_infra.py
python scripts/evaluate_social_relevance.py --cases 5000
python scripts/evaluate_public_domain_social_corpus.py --sources 300
```

The public-domain run requires the official `pg_catalog.csv` offline catalog at
`.tmp/pg_catalog.csv`. Model calls are not required. If an inference provider
has no remaining quota, all deterministic retrieval, corpus, parser, graph,
context, security, and infrastructure checks continue normally.

## Limits

These tests are strong regression evidence, not proof of parity with Google or
TikTok. Those systems learn from enormous populations and feedback streams;
Thought Pins is intentionally private and user-specific. Its quality target is
different: exact personal recall, provenance, correction, temporal coherence,
and low irrelevant intrusion. Any future learned reranker must train on
consented private feedback or de-identified evaluation judgments, preserve
monotonic safety constraints, and beat this fixed baseline on source-separated
holdouts before serving.
