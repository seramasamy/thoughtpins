# Memory design notes

Design review and measurements: 2026-07-21. Documentation revised: 2026-09-12.

## Decision

Keep the memory runtime in Thought Pins' existing modules. The application
already owns journal and source records, tenant scoping, typed entities and
relationships, retrieval, conversation persistence, account deletion and vault
export. Embedding another agent runtime would add an orchestration layer whose
data ownership and lifecycle would also need to be defined and tested.

Hermes Agent informed this review as a related system. Its current documented
scope and other alternatives are listed in [ALTERNATIVES.md](ALTERNATIVES.md).

The useful Hermes concepts are architectural, not dependency-level:

- Treat remembered content as untrusted evidence when assembling prompts.
- Keep a small stable user/profile prefix while retrieving detail per request.
- Preserve direct search over durable conversation history.
- Let users control what becomes durable memory.

Thought Pins now applies the first concept through `memory/context_safety.py`; the remaining concepts already exist through response profiles, durable chat records, hybrid search, journal/chat routing, correction, undo, and explicit save controls.

## Evidence and open questions

The table maps implemented behavior to the validation still needed. Measurements
in this document are historical notes from July 2026; they do not describe a
fresh run against the current deployment.

| Area | Implemented evidence | Further validation |
| --- | --- | --- |
| Capture and portability | Source records, corrections, account export/delete and vault interoperability | Real-device and operational lifecycle rehearsals |
| Retrieval and provenance | Hybrid candidate generation, bounded ranking, attributed claims and temporal metadata | Larger untouched evaluations and modern baselines |
| Context assembly | Privacy projection, evidence planning, token bounds and untrusted-input labels | Live-model grounding and prompt-injection evaluation |
| Evaluation | Deterministic fixtures, pinned external adapters and policy replay | Confidence intervals, untouched holdouts and artifact publication |
| Tenant isolation | Scoped queries, RLS tests and coordinated derived-index deletion | Deployment-specific role, failure and restore verification |
| Operations | Recorded local Compose, recovery and load rehearsals | Managed-infrastructure load, failover and quota evidence |

The recorded local rehearsal restored PostgreSQL, the vault volume,
and an authenticated Qdrant collection, then sustained 100 concurrent health
clients with zero request failures and a p95 below 500 ms. A separate
ten-tenant run completed all queued jobs with no request, isolation, dead-letter,
or cleanup failures at a 353.474 ms p95. Scoped worker, Redis, PostgreSQL, and
vector outages were detected and recovered without restarting the API. On
2026-07-21, a
separate disposable configured-inference workflow passed 15/15 checks across
six entries, 38 atomic memories, reminder splitting, expense linkage,
attribution, retraction, non-orphaned hearsay, places, causal metadata, and two
memory-backed answers. These results describe one local topology and configured
account. Managed production behavior requires its own measurements.

## Retrieval Evidence

The July deterministic offline evaluation contained 18 labeled checks,
including 17 ranked cases, for
rare clues, dates, people, places, sources, temporal updates, multi-hop bridges,
and source-versus-lived-memory separation. Relevance labels are maintained
outside the ranker. Metrics deduplicate multiple retrieval paths that resolve
to the same source event, preventing lexical, vector, and graph agreement from
inflating quality.

At cutoff 10, that fixture reported:

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
policy. The generated 5,000-case social benchmark supplies same-person,
same-place, high-star, and uncertain-claim decoys, while the 300-book corpus
tests source-separated literary passages. The serving policy is
`social-episodic-v2`, and all corpus-generation logic is excluded from
request-time code.

The external replay adds 46 LongMemEval questions and 25 LitBank speaker
queries. On the same LongMemEval candidates, Recall@1 was 0.8478 for BM25 and
0.8696 for Thought Pins: one additional correct top result. MRR was 0.9065 and
0.9174 respectively, with
1.000 Recall@5. LitBank reaches 1.000 Recall@1 and MRR for all speakers and for
the 16 minor-speaker cases. The compact fixture's saturated ablations are not
used as evidence that every feature is necessary. The holdout was revisited,
making this a confirmatory replay. Candidate-generation recall and live-model
answers are outside its scope. Full methodology is in
[EXTERNAL_MEMORY_BENCHMARKS.md](EXTERNAL_MEMORY_BENCHMARKS.md).

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

## Retrieval Invariants

The following contracts are covered by
[search recovery tests](../../tests/test_search_resilience.py),
[ranking context tests](../../tests/test_ranking_context.py) and
[ranking regressions](../../tests/test_retrieval_robustness.py).

**Candidate identity is deterministic.** The same corpus and query produce the
same candidate identities on every process and every run. This is a
prerequisite for policy replay: an evaluation that replays one
candidate pool under several ranking policies cannot compare runs if the
identities move. Graph evidence carries no row of its own, so its identity is a
BLAKE2b digest of the fact text. It previously used Python's builtin `hash()`,
which is salted per interpreter — the same fact had one identity in the API,
another in the worker, and another on the next run.

**Collector failures are isolated.** Eight channels propose candidates through
sequential calls, with entity filtering enabled only when supplied. Each has an
exception boundary. A failed collector can reduce recall while the remaining
collectors continue; enough missing evidence can still make a question
unanswerable. The channels are complementary, not statistically independent.

**Query and candidate features are reused within a rerank.** Scoring,
diversification and coverage repair share one query interpretation and memoized
candidate facets. Tests compare cached features with direct recomputation.
This avoids repeated parsing; it does not make every selection operation
linear, and it is not a production latency measurement.

**Ranking parameters are declared and bounded.** `RankingWeights` contains
20 parameters, including coefficients, caps, neutral points and gating floors.
Construction rejects non-finite values and parameters outside their declared
bounds. These bounds constrain individual contributions; their effect on the
final ordering still depends on the feature values and selection policy.

## Graph Backend

The internal SQL graph remains authoritative. A Graphiti shadow adapter is
available for local evaluation. Production validation rejects external graph
and shadow modes until tenant-scoped deletion is supported and verified.
Promotion also needs recall, correction, provenance and recovery measurements
against the selected backend.

## Open operational checks

- Repeat the local RLS, queue, vector recovery, and restore proof against the
  exact managed staging services and non-owner production role.
- Long-running managed-staging soak with production network policy, autoscaling,
  alerting, and billing limits.
- Long-horizon retrieval evaluation over larger, messy personal corpora.
- Point-in-time recovery and regional failure drills for the selected managed
  database; verify vector rebuild and graph reconciliation after restore.
- Prompt-injection red-team cases against the configured production model.
- Cost, latency, and recall curves for smart versus full-context thresholds.
