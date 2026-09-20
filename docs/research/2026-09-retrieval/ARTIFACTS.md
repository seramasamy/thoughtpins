# Public artifact contract

The artifacts are an allowlisted projection of the completed experiments,
prepared after the final evaluation. They contain public dataset identifiers
and derived numeric data, not personal notes, source passage text, credentials,
provider request IDs, private machine paths, or account balances.

| File | Purpose |
| --- | --- |
| `manifest.json` | SHA-256 hashes of public artifacts and replay/scoring source; UTF-8 CRLF normalized to LF for checkout portability |
| `queries.json` | Final query IDs, corpus, dependence group, date, diagnostic slice and source-ID relevance judgments |
| `local-rankings.jsonl` | All 13 archived local arms, including B2's existing text-based policy |
| `model-decisions.jsonl` | All 1,528 model decisions, original and shuffled candidate IDs, output strings, finish status, exact fallback, cost and latency |
| `final-features.jsonl` | Every final source's four bounded features, tuned lexical score and RRF lexical score; no gold features |
| `training-pairs.jsonl` | All positive and eight fixed BM25-negative feature rows for each of 396 fitting queries; labels used only during training |
| `config.json` | Selected weights, BM25 settings, group priors, model IDs, context limits and selection criterion |
| `trials.json` | All 53 fixed-grid trials, five simpler cross-fitted families and 12 robust configurations with eight-fold fit settings |
| `expected.json` | Archived aggregate metrics, counts, paired effects and decisions used to verify independently recomputed results |
| `historical.jsonl` | Source-ID judgments and predictions on the old 43-question historical and distinct 46-question validation splits |
| `nfcorpus.jsonl` | Previously exposed transfer predictions and graded relevance judgments; see CC BY-SA notice |
| `*-expected.json` | Archived historical/transfer tables checked by replay |
| `splits.json`, `exposure.json` | Eligibility, overlap exclusions, data roles and later exposure status |
| `baseline-amendment.json` | Pre-label addition of the exact previous control; original pilot variant retained |
| `datasets.json` | Original public download URLs, exact revisions/digests and licenses |
| `costs.json`, `resources.json` | Conservative usage and timing summaries with scope limitations |
| `attempt-costs.jsonl`, `archived-prices.json` | 2,210 anonymous per-attempt token/charge records and the historical price table, reconciled by replay |
| `robustness.json` | 14 synthetic and 20 repeat/permutation decisions, including original comparison rankings and scorer-only judgments |
| `diagnostics.json` | Post-score descriptive effects, topic results and slice decomposition; not a new hypothesis family |
| `prior-study-summary.json` | Original negative study summary, archived rather than independently recomputed by this package |
| `provenance.json` | Original code commit, source-run hash attestations and numerical environment |

The replay's regenerated JSON includes all primary/ablation arm metrics,
five corrected comparisons per corpus and the historical/transfer tables.
`expected.json` is a comparator, never an input to metric calculation or
weight fitting. `queries.json` gold labels enter only the evaluator. Training
features are distinct from final numeric features. Live model calls are
disabled by the replay entry point.

The published feature cache is deliberately smaller than the original runs:
it omits corpus passages, full provider prompts, raw embeddings, and private
operational files. It is enough to refit the selected model and rerank all
final candidates without buying inference. It cannot independently verify
that a stored feature was correctly derived from a raw passage. The complete
local audit verified those feature hashes before this projection was made.

To run a new raw-corpus experiment, acquire the exact public datasets listed
in `datasets.json`, verify their hashes and licenses, use the public adapters
in `research_data.py`, lexical/dense interfaces in `research_retrieval.py`,
and source-unit evaluation in `research_engine.py`. New embeddings and model
responses require your own providers and a new protocol, exposure manifest,
budget and attempt ledger. The public final labels are now exposed and cannot
serve as a new untouched holdout. The historical Fireworks adapter is not
invoked by any replay or CI job; its archived prices and fixed study cap are
not a recommendation for a new paid run.
