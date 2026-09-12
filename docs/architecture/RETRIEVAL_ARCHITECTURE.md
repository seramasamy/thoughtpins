# How recall works

Thought Pins combines typed personal memory with hybrid retrieval and a
bounded ranking policy. Source records, attribution, privacy scope and temporal
metadata pass through extraction, retrieval and context assembly. The ranker
uses explicit heuristics; its score is not a probability of answer correctness.

This walkthrough describes the current implementation. Historical measurements
are identified separately from executable contracts and proposed experiments.

## 1. Preserve the source and its interpretation

[Ingestion](../../src/thoughtpins/ingestion/service.py) stores the original
record separately from extracted structure. The [schema](../../src/thoughtpins/db.py)
represents entities and aliases, typed relationships, events and participants,
atomic memories and their source evidence. Source reading and lived journal
experience retain separate provenance.

A memory can carry `valid_from`, `valid_to` and `supersedes_memory_id`, along
with creation and update metadata. These support validity and correction
history. They do not by themselves implement a fully system-versioned temporal
database or prove arbitrary historical queries are answered correctly. Retrieval
and synthesis must still interpret the relevant time and claim status.

For example, “Sarah told me Tom might leave” contains a speaker and uncertainty.
Those qualifiers need to survive extraction and answer generation; retrieving
only “Tom leaves” would change the meaning. The [social evidence module](../../src/thoughtpins/memory/social_relevance.py)
and [evidence planner](../../src/thoughtpins/memory/evidence_plan.py) address
this boundary, with [regression coverage](../../tests/test_retrieval_robustness.py).

## 2. Generate candidates through complementary paths

[search.py](../../src/thoughtpins/memory/search.py) separates candidate
collection from ordering. It exposes eight paths; the entity-filter path runs
only when a filter is supplied. These are distinct retrieval mechanisms, not
statistically independent measurements.

| Path | Contribution | Important limitation |
| --- | --- | --- |
| `entity_filter` | Memories attached to a resolved entity | Requires the correct entity scope |
| `exact_phrase` | Literal substrings, including unusual names | Rewording can remove the match |
| `vector` | Semantic similarity through the configured embedding backend | Quality depends on embeddings, indexing and tenant filters |
| `keyword` | Lexical matches over extracted memories | Limited semantic reach |
| `sql_graph` | Memories reached through SQL entity relationships | Depends on extraction and graph coverage |
| `graph_evidence` | Relationship evidence and paths | Sparse or incorrect structure limits the evidence |
| `document_title` | Reading sources identified by title | A title does not establish support inside a document |
| `raw_keyword` | Original entry text, including unextracted material | Falls back to lexical evidence |

A per-channel exception boundary lets other collectors continue after a channel
fails. This improves availability while potentially reducing recall; it does
not guarantee a useful answer during an outage. Candidate identities are stable
across processes, and duplicate proposals accumulate retrieval sources and
source ranks before reranking.

Public request paths supply authenticated tenant scope and applicable privacy
policy. Vector filtering and SQL authorization provide complementary checks.
Local review modes have different authentication rules and must remain isolated
from production.

![Five stages: scoped question, eight retrieval paths, merge and ranking, evidence context, model response.](assets/retrieval-pipeline.svg)

Scope → collect → merge/rank/select → build context → respond. The diagram is
a static SVG, with the channel and ranking contracts described in the text below.

## 3. Fuse ranks and evidence explicitly

[RankingWeights](../../src/thoughtpins/memory/ranking.py) is an immutable
configuration with 20 finite, bounded parameters. Some are coefficients; others
are caps, neutral points and gating floors. Validation rejects an unbounded new
parameter. [RankingPolicy](../../src/thoughtpins/memory/ranking.py) independently
switches lexical evidence, rank fusion, structural priors, salience, social
evidence and coverage/diversity behavior for ablation.

For candidate $d$, reciprocal rank fusion is:

$$RRF(d) = \sum_{c \in C_d} \frac{1}{60 + \max(1,\operatorname{rank}_c(d))}$$

The collector scores are heterogeneous; RRF supplies an ordering signal without
requiring their raw scores to share units. The code also retains a bounded base
score and explicit lexical features. It is not a pure RRF ranker.

The defaults first compute a blended retrieval value:

```text
b = clip(channel_base, 0, 1)
f = 0.68 b + 0.18 lexical + 0.05 phrase + 0.04 proximity + 1.25 RRF
consensus = min(0.045, 0.018 log(1 + number_of_retrieval_sources))
r = clip(max(b, f) + consensus + recency + document_prior + graph_prior, 0, 1)
```

The document and graph priors are each 0.015 when applicable. A separate stage
adds query-conditioned and preference signals:

```text
score = clip(
    0.93 r
    + 0.06 temporal_window_match
    + gated_user_importance
    + 0.02 (entry_salience - 0.5)
    + 0.02 (memory_type_salience - 0.70)
    + 0.15 social_focus × social_utility
    - 0.035 max(0.6, social_focus) × factualization_risk,
    0, 1
)
```

These equations describe the default enabled feature families;
`_calibrated_score` is the executable specification, including missing-value
handling and ablation switches. The function's historical name does not mean
its output is probability-calibrated. Comparing coefficient magnitudes alone
also does not establish feature importance: the inputs have different ranges.

The user-importance contribution is damped for socially specific questions when
the candidate misses the requested identity or intent. Stars express a person's
preference, not the truth of a statement. An unattributed uncertain claim gets
a penalty even when the query is phrased as a factual question. These are
explicit design constraints, with [social ranking tests](../../tests/test_social_benchmark.py)
and [salience tests](../../tests/test_salience.py), rather than a general proof
that priors can never change a ranking incorrectly.

## 4. Select evidence that covers the question

`rerank_results` receives candidates, a policy, a result limit and an optional
`as_of_date`. Pin the date for reproducible experiments: temporal features
otherwise use the current date. Clone candidates with `clone_candidates_for_rerank`
before comparing policies; that restores their pre-fusion scores instead of
ranking an already-ranked pool again.

The default policy can use maximal marginal relevance with a diversity
coefficient of 0.82. It skips that work for simple pools when the adaptive check
finds no need for diversification. Requested-aspect and narrative-coverage
repairs retain useful complementary evidence. This is a listwise selection
stage after pointwise scoring, not merely sorting the nearest vectors.

[Ranking-context tests](../../tests/test_ranking_context.py) exercise reuse of
query interpretation and facet profiles. [Query-cost tests](../../tests/test_context_query_cost.py)
check bounded SQL growth as corpus dimensions increase. They are performance
regressions, not production latency measurements.

## 5. Build a bounded, labelled context

[context_package.py](../../src/thoughtpins/memory/context_package.py),
[context_sections.py](../../src/thoughtpins/memory/context_sections.py) and the
[evidence plan](../../src/thoughtpins/memory/evidence_plan.py) assemble sources,
conversation history and navigational context within a budget. Attribution,
uncertainty and privacy projection remain relevant after ranking.

[context_safety.py](../../src/thoughtpins/memory/context_safety.py) labels
retrieved text as untrusted evidence and identifies instruction-shaped content.
The [fixture tests](../../tests/test_context_safety.py) exercise that boundary.
A live model may still hallucinate or follow adversarial text; model-based
red-teaming and answer-grounding evaluation are separate requirements.

## 6. Interpret the evaluation at the right level

The [external evaluation protocol](EXTERNAL_MEMORY_BENCHMARKS.md) records a
July 21, 2026 replay. Its LongMemEval adapter compares policies over the same
candidate sessions; it does not run the entire live ingestion/retrieval/answer
stack.

| Documented experiment | Sample | Result | What it supports |
| --- | ---: | --- | --- |
| LongMemEval session reranking | 46 cases | Recall@1: BM25 0.8478, Thought Pins 0.8696 | One additional correct top-ranked session on this sample |
| LongMemEval coverage | Same 46 | Both reach 1.0 Recall@5/10 | Coverage of the supplied candidates on this sample |
| LitBank attribution ranking | 25 cases, including 16 minor-speaker cases | Recall@1/MRR 1.0 in the documented replay | A small controlled attribution regression |
| Generated literary questions | 300 books | Saturated documented metrics | Broad regression coverage; labels share their source passages |

The holdout was later revisited, so the recorded run is confirmatory rather
than a new untouched estimate. The full 500-question LongMemEval run and a
comparison against modern dense or learned rerankers are outstanding. Perfect
Recall@10 on 46 supplied candidate sets does not establish that retrieval is
solved, and none of these values measures live-model answer accuracy.

The protocol records dataset pins, licenses, partition rules, calibration
choices and reproduction commands. Benchmark corpora and generated reports stay
in ignored local paths; they are never copied into product accounts.

## Reproduction and open questions

The following checks exercise different parts of the pipeline:

1. Trace one attributed or corrected statement from source to context.
2. Replay a fixed candidate pool with a pinned date under policy ablations.
3. Inspect failures by question type, uncertainty, temporal span and named entity.
4. Compare candidate-generation recall separately from reranking and final answers.
5. Repeat on untouched larger data with dense/learned baselines, paired
   uncertainty estimates, latency and cost measurements.
6. Test live-model prompt injection, tenant isolation, interrupted ingestion and
   deletion recovery independently of retrieval quality.

The fixtures and replay tools cover the implemented contracts. Larger holdouts,
live-model behavior and production cost measurements remain separate work.
