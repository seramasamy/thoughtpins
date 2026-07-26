# Technical Review Guide

This is the shortest path through Thought Pins for an engineering review. The
repository contains a provider-neutral memory backend, responsive web client,
public site, and native iOS/Android review shells. Telegram is an optional
adapter; product behavior belongs in shared modules.

## Run The Local Review Build

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
alembic upgrade head
python scripts/seed_local_demo_corpus.py --json
cd frontend
npm ci
npm run build
cd ..
python -m uvicorn thoughtpins.api:app --host 127.0.0.1 --port 8420
```

Open `http://127.0.0.1:8420/` for the site and
`http://127.0.0.1:8420/app/` for the local app. The fictional seed is
idempotent and tenant-scoped. It creates a coherent seven-day timeline with
journals, sources, graph relationships, explicit ratings, and one encrypted
private reflection.

## Architectural Boundaries

- `ingestion/` classifies and extracts durable structure from captured text.
- `memory/` owns hybrid retrieval, salience, vectors, graph projection, and
  maintenance. It cannot import API, Telegram, or founder transports.
- `chat/` owns cross-surface conversation behavior, bounded context, durable
  turns, and degraded-mode responses.
- `vault/` owns portable Markdown, typed properties, Bases, JSON Canvas,
  import/export, privacy projection, and Obsidian acceptance validation. See
  `OBSIDIAN_INTEROPERABILITY.md` for the versioned format boundary.
- `api_routes/`, `bot/`, and native/web clients are adapters around those
  shared capabilities.
- `demo/` is a deterministic reviewer fixture; production routes never depend
  on it.

The executable architecture policy is in
`deploy/quality/architecture-budget.json`. It prevents dependency inversion,
caps new-module size, and applies exact size ratchets to the remaining large
adapters and stylesheets so they may shrink but cannot grow.

## Memory Ranking

Retrieval fuses lexical, semantic, graph, phrase, temporal, and provenance
signals. Exact evidence remains dominant. `memory/salience.py` provides a
versioned and explainable prior for tie-breaking and recap ordering:

- bounded exponential saturation prevents raw frequency from dominating;
- structural role distinguishes agency and direct subject facts from passive
  co-occurrence;
- topic entropy, source diversity, and temporal persistence reward independent
  support;
- a symmetric Beta-posterior spread reports epistemic uncertainty over an
  effective evidence count;
- duplicate mentions receive only logarithmically capped credit;
- a 1-5 user rating is monotonic but bounded, and never becomes a truth score.

Each stored score includes normalized signals and exact contributions. The
public-domain literary fixture checks protagonist, recurring ally,
case-specific agency, and one-off-character ordering without shipping book
text as product data.

## Privacy Semantics

The chat control **Use private memories** governs recall only. It decides
whether an already-private entry may be supplied as evidence for a reply. It
does not mark the outgoing message private. The unchecked state is the safe
default: private memories stay out of search and answer context. Server policy
can disable private model context entirely, the account preference supplies a
default, and an individual request may opt out. Private text is encrypted at
rest when the deployment key is configured.

Portable user exports intentionally omit third-party source text while
retaining user-authored notes, source metadata, and links. Account export and
deletion are first-class API and client workflows.

Vector retrieval applies the authenticated `user_id` inside each supported
backend before candidate text reaches ranking, then SQL scoping and PostgreSQL
RLS provide independent enforcement. In-memory and FAISS indexes rebuild on
deletion; Chroma and Qdrant delete explicit point IDs. External graph adapters
are deliberately rejected by production validation until their tenant-scoped
deletion API is proven for the selected backend.

The deployment contract deliberately separates developer convenience from
multi-process correctness. Founder development can use `qdrant_local`;
staging and production require `qdrant_remote`, an API key, and a live health
probe so API and worker processes share one authoritative derived index.
Account deletion removes vector points before committing relational erasure.
If that cleanup cannot be confirmed, the request returns a retryable failure
and leaves the account active rather than claiming a partial deletion.
PostgreSQL tenant writes acquire a shared active-user row lock; deletion holds
the exclusive lock through vector, retained-voice, and relational cleanup.
Long-running extraction checks active state again before its final commit, so
an already-authorized worker cannot recreate data after erasure begins.
Qdrant erasure enumerates every `journal_memories_*` collection, including old
embedding dimensions. Production refuses surprise dimension drift and requires
a controlled reindex, preventing silent index loss and orphaned derived text.

Refresh tokens are one-time credentials. Rotation claims the session with an
atomic conditional update before issuing a successor, and the test suite forces
two requests through the initial lookup concurrently to prove only one wins.
Sign in with Apple account deletion revokes the stored refresh credential
first. A transient provider failure preserves both the local account and the
encrypted credential for a retry instead of losing the only revocation handle.

Redis rate limiting is fail-closed outside local development. A short reconnect
circuit avoids a retry storm, and the API returns a stable `503` rather than
silently degrading to per-process counters that can be bypassed across replicas.

Asynchronous ingestion uses the relational job row as a compact transactional
outbox. Producers atomically move `pending/retry -> queued` before publishing;
a broker failure restores `retry` without losing the user's text. Workers claim
`pending/retry/queued -> running` with a conditional update, so duplicate broker
delivery cannot run extraction twice. `queued_at_utc` distinguishes a genuinely
stale handoff from an old job retried recently. A throttled relay runs inside
the worker process and recovers pending jobs, stale handoffs, and interrupted
claims even though production API startup recovery is deliberately disabled.
This provides idempotent at-least-once delivery; it does not make external model
calls transactional, so downstream persistence keeps its own deduplication key.

## Verification

```powershell
python -m pytest -q
python scripts/release_check.py --strict-quality
cd frontend
npm run smoke:web
npm run smoke:site
npm run smoke:cross-browser
```

The release gate compiles code, runs architecture and migration checks, scans
public exports and logs, validates free-launch and store policies, builds the
frontend, checks source-level native readiness, and audits Python and frontend
dependencies. Browser tests cover desktop, current and small phones, tablets,
landscape layouts, keyboard behavior, reduced motion, dark appearance, and
automated accessibility.

## Honest Release Boundary

Source checks on Windows do not replace a signed Xcode archive, simulator and
device testing, VoiceOver review, TestFlight, or App Store Connect validation.
Live PostgreSQL RLS proof, production infrastructure, credential rotation, and
legal-owner review also remain release-owner gates. Apache-2.0 is declared for
the repository, subject to the owner's final publication approval. Known
structural debt and exit criteria are tracked in `TECHNICAL_DEBT_REGISTER.md`
rather than being hidden behind a claim of zero debt.
