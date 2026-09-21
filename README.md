<div align="center">

<img src=".github/assets/repository-banner.svg" alt="Thought Pins — your memory, connected. Open-source personal memory with structured recall and human control." width="100%">

Inspired by [David Rockefeller's card file](https://www.wsj.com/articles/david-rockefellers-famous-rolodex-is-astonishing-heres-a-first-peek-1512494592): remember the people you meet and the moments you share. Thought Pins brings that habit into a searchable personal record, with memories linked to their sources and exports you can keep.

[![CI](https://github.com/seramasamy/thoughtpins/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/seramasamy/thoughtpins/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-b6afff)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.13-3776ab)](.python-version)
[![SwiftUI](https://img.shields.io/badge/iOS-SwiftUI-e8612b)](mobile/ios/ThoughtPinsNative/README.md)

**Open-source journaling with structured recall and portable exports.**

[Website](https://thoughtpins.com/#product) · [Run locally](#run-locally) · [Codebase walkthrough](docs/architecture/TECHNICAL_REVIEW_GUIDE.md) · [Documentation](docs/README.md)

</div>

I originally built Thought Pins for my own use. I decided to open-source it
in case anyone else found it useful and wanted to use or adapt it.

## A personal record you can return to

Thought Pins turns journal notes, conversations, voice notes, and saved reading
into a connected record of people, places, events, and ideas. Ask about a past
moment, inspect its source, or export your own record as plain files.

The product includes a responsive React web app, a native SwiftUI iPhone/iPad
app, a FastAPI backend, and an Obsidian-compatible vault. Five destinations —
**Recap, People, Chat, Places, and Pins** — keep the experience consistent across
screens. Android has a separate client and build checks.

<img src="site/assets/product-chat-desktop.png" alt="The Thought Pins desktop web app, with a conversation workspace and the five primary destinations." width="100%">

*Product capture uses a fictional account. [Mobile and desktop previews](https://thoughtpins.com/#product).*

The project is in active development. Source, automated checks, and setup
instructions are public; hosted availability and store distribution are
separate release decisions. See [validation and limits](#validation-and-limits)
for what the evidence supports.

### Capture in the web app

| Input | Current behavior and limits |
| --- | --- |
| Voice note | Record, listen back, choose journal or reference source, then explicitly save or discard. A failed save keeps the in-memory recording for retry with the same request identity. Leaving the view or refreshing discards an unsaved recording. |
| Phone photo or screenshot | Apply the photo's orientation before local OCR. Printed text works best; handwriting, equations, and page layout fidelity are not established. |
| PDF and text notes | Extract selectable PDF text from up to 100 pages; report page limits and pages without readable text. Image-only PDFs need page images or pasted text. Files are limited to 25 MB. |
| Presentations and homework | Export DOCX/PPTX to a PDF with selectable text, or paste the text. Direct Office-file parsing is not implemented. |
| Article link | Save readable authorized content when available. A saved link is distinct from extracted text; the app does not bypass access controls. |

Uploads distinguish unreadable, partial, queued, and completed extraction.
Attachments in Chat default to reference sources, with an explicit journal
choice; new recordings default to the personal journal. Source browsing can
page past the first 100 items and search titles, authors, and sites across the
user's library. Incoming replies preserve the reader's position in chat history.

The next product evidence should come from observed web capture/recall tasks
with 5–10 consenting users and a separately scored end-to-end answer evaluation.
Automated workflow checks and retrieval scores do not establish adoption,
retention, transcription accuracy, or answer accuracy. Further native expansion
and ranking complexity should follow measured failures in those workflows.

## Alternatives, briefly

Thought Pins groups journal capture, people and place views, source retrieval,
and export in one application. The tools below overlap with different parts of
that workflow.

| Alternative and focus | When Thought Pins helps |
| --- | --- |
| [ChatGPT](https://learn.chatgpt.com/docs/customization/memories) / [Claude](https://support.claude.com/en/articles/11817273-use-claude-s-chat-search-and-memory-to-build-on-previous-context): general assistants with memory | A dedicated journal, people/place views, and an inspectable memory pipeline. |
| [Claudian](https://github.com/YishenTu/claudian) / [Copilot for Obsidian](https://www.obsidiancopilot.com/en): agents and search inside your vault | Capture into a structured personal record; keep Obsidian as a portable export. |
| [Gemini Notebook, formerly NotebookLM](https://workspace.google.com/products/gemini-notebook/): research grounded in sources | Connect saved reading with your own experiences and relationships. |
| [Mem](https://help.mem.ai/features/search), [Reflect](https://reflect.app/), [Tana Outliner](https://outliner.tana.inc/): connected notes and AI workflows | A predefined journal-to-memory workflow, with self-hostable source code. |
| [Khoj](https://docs.khoj.dev/): open-source personal AI over files and the web | An experience organized around Recap, People, Chat, Places, and Pins. |
| [Mem0](https://github.com/mem0ai/mem0) / [Zep](https://help.getzep.com/concepts): memory infrastructure for developers | A user-facing app with capture, consent, export, and deletion already wired together. |
| [Hermes Agent](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory/) / [OpenClaw](https://docs.openclaw.ai/concepts/memory): agents with persistent memory and tools | A focused personal archive with explicit source and account lifecycle controls. |

These tools overlap: memory, graphs, citations, privacy controls, and exports
are not unique to Thought Pins. This is a workflow comparison, not a quality
ranking. [Comparison sources and scope](docs/architecture/ALTERNATIVES.md)
were checked against first-party documentation on 11 September 2026.

## How recall works

The central problem is preserving a useful personal record while extraction,
retrieval, model responses, and network delivery can all be imperfect. Thought
Pins keeps durable source records separate from derived memory and gives each
stage an inspectable contract.

| Mechanism | Implementation and purpose |
| --- | --- |
| **Typed extraction and provenance** | Bounded ontology, entity resolution, attributed claims, temporal validity and supersession preserve the relationship between a memory and its source. [Ingestion](src/thoughtpins/ingestion/service.py) · [Schema](src/thoughtpins/db.py) |
| **Hybrid candidate generation** | Eight retrieval paths combine exact phrases, lexical matches, embeddings, entity/graph evidence and source titles. An unavailable channel can degrade recall without aborting all search. [Search](src/thoughtpins/memory/search.py) |
| **Replayable ranking** | Reciprocal rank fusion, bounded relevance/salience signals, social attribution penalties, and adaptive diversity/coverage selection. The ranking policy exposes 20 validated parameters and explicit ablation switches. [Ranker](src/thoughtpins/memory/ranking.py) |
| **Evidence-aware context** | Query-specific evidence planning, source labels and token budgeting retain attribution and mark retrieved text as untrusted input. [Evidence plan](src/thoughtpins/memory/evidence_plan.py) · [Context](src/thoughtpins/memory/context_package.py) |
| **Durable asynchronous work** | Relational job claims, broker handoff recovery and deduplicated persistence address interrupted and repeated delivery. [Job delivery](docs/architecture/TECHNICAL_REVIEW_GUIDE.md#job-delivery) |
| **Tenant and lifecycle boundaries** | User-scoped storage, PostgreSQL RLS, private-recall controls, token rotation, export and coordinated deletion across derived indexes. [RLS verification](scripts/verify_postgres_rls.py) · [Lifecycle](src/thoughtpins/data_lifecycle.py) |

### Eight-channel retrieval, from question to evidence

On capture, original sources and extracted entities, relationships and memories
are persisted in SQL; vector and graph projections provide additional access
paths. SQL holds the authoritative records, and supported derived indexes can
be rebuilt. At query time, the following stages assemble evidence for a reply.

![Five stages: scoped question, eight retrieval paths, merge and ranking, evidence context, model response.](docs/architecture/assets/retrieval-pipeline.svg)

Scope → collect → merge/rank/select → build context → respond. The diagram is
a static SVG, with the channel and ranking contracts described in the text below.

The channel groups show complementary mechanisms, not parallel execution or
independent votes. The current collectors run sequentially; `entity_filter`
runs only when supplied. Each collector has an exception boundary, and losing
a channel can reduce recall. Vector hits are checked against scoped SQL
records before admission. The lexical channels use the project's token/phrase
scoring; BM25 is a separate evaluation baseline.

A rare name can survive literal lookup when its
embedding match is weak. A paraphrase can benefit from vectors. Graph expansion
can reach related memories, while raw-entry lookup can recover wording that
extraction omitted. These are design motivations; channel ablations determine
their measured contribution on a given workload.

Duplicate candidate identities retain
the channels that found them and their ranks. Reciprocal rank fusion contributes
`RRF(d) = Σc 1 / (60 + max(1, rank_c(d)))`; the final score also uses bounded
lexical, temporal, salience and social-attribution features. The 20 validated
ranking parameters define a heuristic policy, not a learned reranker or a
probability of correctness. Adaptive maximal marginal relevance (MMR) reduces
redundancy, and coverage checks retain evidence for the question's different
aspects. The evidence plan and context budget then prepare labelled material
for the response model.

Candidate generation, fixed-pool ranking and live-model answers are separate
evaluation targets. Ranking experiments replay a cloned candidate pool with a pinned
`as_of_date` under policy ablations and measure source-level Recall@k, MRR/nDCG
and evidence coverage. The
[search recovery tests](tests/test_search_resilience.py),
[recall tests](tests/test_search_recall.py) and
[ranking regressions](tests/test_retrieval_robustness.py) cover concrete failure
cases. The [September research study](docs/research/2026-09-retrieval/README.md)
adds held-out query evaluation, dense and learned controls, paired uncertainty,
and experimental cost measurements. Production latency and answer quality
remain separate measurements.

The [algorithm walkthrough](docs/architecture/RETRIEVAL_ARCHITECTURE.md) links
the equations to their implementation. The
[evaluation protocol](docs/architecture/EXTERNAL_MEMORY_BENCHMARKS.md) records
datasets, reproduction commands and experimental limits. The
[codebase walkthrough](docs/architecture/TECHNICAL_REVIEW_GUIDE.md) covers the
remaining application boundaries. These references are optional; the app can
be used without reading the implementation.

## User control is part of the design

- **Keep the source.** Extracted memories retain provenance. Editing a chat
  turn does not silently delete journal entries it previously created.
- **Choose private recall.** Already-private memories are excluded by default;
  including them requires the applicable account/request choice and server
  policy. Private text encryption uses the deployment's configured key.
- **Take your record with you.** Account JSON and an Obsidian-compatible vault
  provide portable exports. Third-party source text follows the export policy.
- **Delete through the product.** Account deletion coordinates relational,
  vector and retained-audio cleanup; it reports failure when required cleanup
  cannot be confirmed.
- **Keep external content in its place.** Journals and documents enter model
  context as evidence. These defenses reduce exposure to instruction injection;
  they do not guarantee a model will never follow malicious content.

[Security policy](SECURITY.md) · [Privacy](https://thoughtpins.com/privacy) · [Vault contract](docs/architecture/OBSIDIAN_INTEROPERABILITY.md)

## Run locally

Use the pinned Python 3.13 environment and Node.js 22 for the web build.
Python compatibility is declared in [pyproject.toml](pyproject.toml); release
installs resolve through [uv.lock](uv.lock).

```bash
git clone https://github.com/seramasamy/thoughtpins.git
cd thoughtpins
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
cd frontend
npm ci
npm run build
cd ..
python -m thoughtpins.server --api-only
```

Open **http://127.0.0.1:8420/app/**. Default local mode uses SQLite; model-backed
extraction and answers require a configured provider. Do not expose local
no-auth mode to the public internet. Configure the provider using the template's
`LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, and `LLM_API_KEY` settings.

[Windows and full setup](docs/operations/RUNNING.md) · [macOS/iOS setup](apple-submission/MAC_START_HERE.md) · [Production operations](docs/operations/PRODUCTION_RUNBOOK.md)

<a id="whats-unproven"></a>

## Validation and limits

CI runs Python, PostgreSQL, web, Android and container checks. Changes affecting
iOS on `main` also trigger native compilation/archive checks; the workflow and
its individual job results are the source of truth for each commit. The local
strict release command is:

```bash
python scripts/release_check.py --strict-quality
```

[Browser tests](frontend/e2e/) cover authentication, navigation, recovery,
privacy, offline behavior and device layouts. [Website tests](frontend/site-e2e/)
cover previews, keyboard control, appearance and accessibility. [Native UI tests](mobile/ios/ThoughtPinsUIReview/README.md)
exercise the production SwiftUI package against fictional fixtures. Passing
these checks does not replace a signed distribution build or real-device review.

The [September 2026 retrieval study](docs/research/2026-09-retrieval/README.md)
evaluates 182 held-out LongMemEval questions and 200 additional EverMemBench
questions. On LongMemEval, the experimental scorer plus GLM reranking improves
**nDCG@10 from 0.927 to 0.973** versus development-tuned BM25, with complete
support within five sources increasing from **153/182 to 178/182**. The paired
gain passes the registered decision rule (Holm-adjusted p=0.0016).

| Same 182 LongMemEval questions | nDCG@10 | Relevant first source | All supporting sources within five |
| --- | ---: | ---: | ---: |
| Development-tuned BM25 | 0.926680 | 167/182 | 153/182 |
| Previous GLM reranker | 0.966885 | 180/182 | 163/182 |
| Experimental scorer plus GLM | 0.973263 | 174/182 | 178/182 |

The [independent accuracy audit](docs/research/2026-09-retrieval/AUDIT.md)
recalculates the scores and statistics without importing the original evaluator.
Against tuned BM25, nDCG improves on 42 questions, declines on 16 and ties on
124. These questions search their supplied histories of 38-62 sessions each.
An nDCG score of 0.973 is a ranking measure, not 97.3% answer accuracy.

The local scorer alone does not pass every guardrail, and superiority over the
previous GLM reranker or the simpler matched GLM-on-BM25 control is unproven.
EverMemBench has only five shared topics and insufficient independent groups
for a confirmed gain. These are offline source-retrieval experiments, not
answer accuracy, a production algorithm change, or a general benchmark win.
The report includes negative results, ablations, cost and a no-key replay:

```bash
python -m pip install -r docs/research/2026-09-retrieval/replay-requirements.txt
python scripts/replay_retrieval_study.py
python scripts/audit_retrieval_metrics.py
```

The [corrected July comparison](docs/architecture/EXTERNAL_MEMORY_BENCHMARKS.md#corrected-retrieval-metrics)
has 43 answerable cases after excluding three abstentions: Hit@1 is 38/43 for
the existing policy and 37/43 for BM25. Its old "Recall@5/10=1.0" label meant
any-evidence Hit@k, not complete support. The full 500-question generated-answer
evaluation, new-topic memory generalization and live-user quality remain open.

The repository also includes deterministic regression suites and public-domain
literary evaluations. Generated questions from the same passages test
regressions; they are not independent evidence of generalization. Production
scale, live provider quality, physical-device behavior and signed TestFlight
readiness require their own recorded evidence.

## Navigate the repository

| Area | Start here |
| --- | --- |
| Ownership and architecture | [Module map](ARCHITECTURE_MODULES.md) |
| Backend and memory engine | [src/thoughtpins/](src/thoughtpins/) |
| Web app and public site | [frontend/](frontend/README.md) · [site/](site/README.md) |
| Native apps | [mobile/](mobile/README.md) |
| Algorithms and evaluation | [Retrieval architecture](docs/architecture/RETRIEVAL_ARCHITECTURE.md) · [Evaluation protocol](docs/architecture/EXTERNAL_MEMORY_BENCHMARKS.md) · [Results and offline replay](docs/research/2026-09-retrieval/README.md) |
| Releases and operations | [Documentation index](docs/README.md) · [Production runbook](docs/operations/PRODUCTION_RUNBOOK.md) |

## Contribute

Read [CONTRIBUTING.md](CONTRIBUTING.md) and the [engineering guide](AGENTS.md)
before changing behavior. Use an issue for reproducible bugs or proposed
improvements. Report security issues through [SECURITY.md](SECURITY.md).

Licensed under [Apache-2.0](LICENSE); see [NOTICE](NOTICE). The software license
does not grant rights to the Thought Pins product names or marks.
