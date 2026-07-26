# Thought Pins Memory Architecture Review

Reviewed: 2026-07-21

## Decision

Thought Pins should not embed Hermes Agent as its memory runtime. Hermes is a broad tool-running agent with session search, a compact persistent profile, and context-file conventions. Thought Pins already owns the harder product-specific layer: durable journal and source records, tenant scoping, typed entities and relationships, temporal corrections, vector and lexical retrieval, graph expansion, provenance, conversation persistence, account deletion, and Obsidian portability. Pulling in a second agent runtime would duplicate orchestration, enlarge the security surface, and blur data ownership.

The useful Hermes concepts are architectural, not dependency-level:

- Treat remembered content as untrusted evidence before prompt injection.
- Keep a small stable user/profile prefix while retrieving detail per request.
- Preserve direct search over durable conversation history.
- Let users control what becomes durable memory.

Thought Pins now applies the first concept through `memory/context_safety.py`; the remaining concepts already exist through response profiles, durable chat records, hybrid search, journal/chat routing, correction, undo, and explicit save controls.

## Current Grade

Overall engineering grade: **9.5/10** for a production-candidate memory layer,
not a claim of production proof.

| Dimension | Grade | Evidence |
| --- | ---: | --- |
| Durable capture and portability | 9.2 | Journal/chat/source records, corrections, export/delete, Obsidian import/export |
| Retrieval quality | 9.7 | Exact and BM25-style lexical signals, embeddings, RRF, graph expansion, social-scene constraints, temporal/diversity priors, bounded contextual salience, and independently labeled LongMemEval/LitBank evaluation |
| Structure and provenance | 9.4 | Typed ontology, attributed claims, claim lifecycle, constrained relationships, source/lived-experience separation, evidence text, versioned prominence signals |
| Context assembly | 9.4 | Smart/full modes, recent conversation, privacy-aligned source counts, navigational map, bounded retrieval, query-conditioned evidence plan, untrusted-evidence envelope |
| Evaluation and repair | 9.7 | Fixed fixtures, public-domain books, 5,000 adversarial scenes, pinned LongMemEval/LitBank adapters, source-separated calibration, audits, reindexing, and correction paths |
| Tenant and lifecycle safety | 8.9 | User-scoped queries, RLS migrations/scripts, encrypted private content, deletion and rating refresh across derived indexes |
| Proven scale and operations | 8.8 | Exact local Compose proof covers non-owner PostgreSQL RLS, Redis/Celery delivery, shared Qdrant snapshot recovery, PostgreSQL/vault restore, bounded readiness, scoped dependency recovery, a ten-tenant authenticated flow, and 100-VU health load; managed staging remains an external gate |

The latest exact-topology local rehearsal restored PostgreSQL, the vault volume,
and an authenticated Qdrant collection, then sustained 100 concurrent health
clients with zero request failures and a p95 below 500 ms. A separate
ten-tenant run completed all queued jobs with no request, isolation, dead-letter,
or cleanup failures at a 353.474 ms p95. Scoped worker, Redis, PostgreSQL, and
vector outages were detected and recovered without restarting the API. On
2026-07-21, a
separate disposable configured-inference workflow passed 15/15 checks across
six entries, 38 atomic memories, reminder splitting, expense linkage,
attribution, retraction, non-orphaned hearsay, places, causal metadata, and two
memory-backed answers. This is strong local evidence under one configured
account, not a claim that the complete workflow is ready for public traffic.

## Retrieval Evidence

The deterministic offline evaluation currently contains 18 labeled checks,
including 17 ranked cases, for
rare clues, dates, people, places, sources, temporal updates, multi-hop bridges,
and source-versus-lived-memory separation. Relevance labels are maintained
outside the ranker. Metrics deduplicate multiple retrieval paths that resolve
to the same source event, preventing lexical, vector, and graph agreement from
inflating quality.

At cutoff 10, the current fixture reports:

| Metric | Result |
| --- | ---: |
| nDCG@10 | 1.000 |
| Recall@10 | 1.000 |
| Mean reciprocal rank | 1.000 |
| MAP@10 | 1.000 |
| Evidence coverage | 1.000 |
| Worst-case nDCG@10 | 1.000 |

Seven policy variants replay the same candidate pool with lexical evidence,
rank fusion, structural priors, salience priors, social evidence, and diversity
disabled in turn.
This compact fixture is saturated, so its ablations do not separate every
policy. The independent 5,000-case social benchmark supplies hard same-person,
same-place, high-star, and uncertain-claim decoys, while the 300-book corpus
tests source-separated literary passages. The serving policy is
`social-episodic-v2`, and all corpus-generation logic is excluded from
request-time code.

The independent holdout adds 46 LongMemEval questions and 25 LitBank speaker
queries. Against the same LongMemEval candidates, Thought Pins improves the
BM25 baseline from 0.8478 to 0.8696 Recall@1 and 0.9065 to 0.9174 MRR, with
1.000 Recall@5. LitBank reaches 1.000 Recall@1 and MRR for all speakers and for
the 16 minor-speaker cases. The compact fixture's saturated ablations are not
used as evidence that every feature is necessary; the external and adversarial
sets supply that separation. Full methodology is in
`EXTERNAL_MEMORY_BENCHMARKS.md`.

## Context Strategy

A one-million-token window is useful as an audit and small-library fallback, not as a reason to resend a lifetime of data on every turn. Full replay increases cost and latency, duplicates irrelevant text, weakens attention to rare evidence, and eventually competes with source documents and the current conversation. The hard token ceiling is not the only limit; retrieval quality can degrade well before it is reached.

The production default should remain hybrid:

1. Stable system policy and explicit response profile.
2. Current conversation plus a bounded recent-history window.
3. Compact navigational map and open loops.
4. Query-specific exact, lexical, vector, temporal, and graph evidence.
5. Full context only when the complete corpus fits the configured threshold or the user requests an audit.

This gives obscure details multiple ways to surface while preserving dates and source provenance. Founder/local use can keep a higher full-context threshold because its corpus and cost are controlled; public multi-user traffic should use smart mode by default.

## Contextual Salience

`salience-v4` keeps explicit 1-5 star feedback separate from inferred
prominence. Entity ranking combines saturating recurrence, structural agency,
graph breadth, extracted-topic entropy, source diversity, temporal persistence,
evidence quality, recency, and a bounded manual prior. Exact query relevance
still dominates retrieval. Rating, undo, and entry-deletion paths immediately
refresh affected entries and cards, and normalized signals are persisted for
debugging and future model-version backfills.

## Social-Episodic Ranking

The serving ranker models an answerable scene rather than treating every
memory as an interchangeable text chunk. It detects facets explicitly requested
by the query: people, attributed statements, place, time, cause, outcome,
relationship, uncertainty, and open loops. Candidate utility remains bounded
and is applied only after candidate retrieval establishes relevance. A
constrained listwise repair reserves limited capacity for requested facets
without allowing a metadata-rich but irrelevant memory to replace exact
evidence.

Statements retain speaker and claim status through extraction, persistence,
ranking, context assembly, and synthesis. Hearsay can rank highly for a rumor
question, but an unattributed uncertain claim receives a factualization-risk
penalty. Stars remain preference signals and are dampened when a candidate does
not answer the explicit social facets or named person in the query. Detailed evidence and
limitations are in `SOCIAL_EPISODIC_RELEVANCE.md`.

## Graph Backend

The internal SQL graph remains authoritative. Graphiti is already available as a shadow adapter and should be promoted only if the same tenant-scoped evaluation set shows a measurable recall gain without weakening deletion, temporal correction, provenance, or operational reliability. A graph product is not automatically a better memory product; the deciding evidence is end-to-end recall quality and lifecycle correctness.

## Remaining Proof

- Repeat the local RLS, queue, vector recovery, and restore proof against the
  exact managed staging services and non-owner production role.
- Long-running managed-staging soak with production network policy, autoscaling,
  alerting, and billing limits.
- Long-horizon retrieval evaluation over larger, messy personal corpora.
- Point-in-time recovery and regional failure drills for the selected managed
  database; verify vector rebuild and graph reconciliation after restore.
- Prompt-injection red-team cases against the configured production model.
- Cost, latency, and recall curves for smart versus full-context thresholds.
