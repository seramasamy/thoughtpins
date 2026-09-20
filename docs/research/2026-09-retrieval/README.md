# September 2026 retrieval study

**The model-assisted experiment improved source retrieval over tuned BM25 on
182 held-out LongMemEval questions: nDCG@10 0.926680 to 0.973263.** Complete
support within five sources increased from 153/182 to 178/182. The paired
nDCG difference was +0.046583, nominal 95% CI [0.021801, 0.072944], with
Holm-adjusted p=0.001600 across five comparisons within this corpus.

This is a local research result. It is not an official full 500-question
LongMemEval answer evaluation, a production deployment, or a claim of general
superiority. The new local scorer did **not** pass all promotion criteria by
itself. The study did **not** establish superiority over the previous GLM
reranker or the simpler matched GLM-on-BM25 control.

The [September 20 accuracy audit](AUDIT.md) independently reproduced the
metrics, paired intervals and corrected p-values, and traced the published
judgments and model decisions back to the original public-data files. This
is a verification of the frozen backtest, not a new performance experiment.
No reported score changed and no additional model calls were made.

## Reproduce without an API key

From a checkout of this publication, with Python 3.13:

```bash
python -m venv .venv
# Linux/macOS: . .venv/bin/activate
# Windows PowerShell: .venv/Scripts/Activate.ps1
python -m pip install -r docs/research/2026-09-retrieval/replay-requirements.txt
python scripts/replay_retrieval_study.py --output reports/retrieval-study-replay.json
python scripts/audit_retrieval_metrics.py --output reports/retrieval-metric-audit.json
```

The command disables network connections before replay, verifies SHA-256
manifests, recomputes the metrics from source-ID judgments and rankings,
repeats paired bootstrap/randomization and Holm correction, validates all
1,528 final model decisions including every fallback, refits the selected
weights from 396 development queries, and reconstructs 12 local arms on each
of 382 final queries from frozen numeric features. Historical and NFCorpus
tables are also recalculated. No database, product installation, credentials,
provider account, source corpus download or paid inference is needed.

This is **cached-feature computational replication**. It does not regenerate
embeddings, reconstruct source text, rerun live GLM inference, or reconstruct
the existing product policy's text features. B2's archived predictions are
rescored. Statistical values are checked within 1e-12; refitted weights within
1e-7 for solver/platform differences; ranking identities must match exactly.
The original full local replay additionally reconstructed text features and
model requests before publication. Its hash attestations are recorded in
[provenance.json](artifacts/provenance.json); those attestations alone do not
independently prove data collection or the time of the local freeze.

The [artifact guide](ARTIFACTS.md), [protocol](PROTOCOL.md),
[mathematics](MATHEMATICS.md), and [dataset/license notices](DATASETS.md)
explain the inputs. Use
[`tests/test_research_publication.py`](../../../tests/test_research_publication.py)
and the other `test_research_*` suites for invariant checks.

The second command uses separate metric, model-decision and statistical
implementations with no imports from the original evaluator. It checks all
17 final arms on both memory corpora and 30 paired metric comparisons. See
[the audit](AUDIT.md) for hand-worked tests and the separate raw-data audit.

## Final results

All memory metrics use binary relevance. nDCG is evaluated at 10; MRR is
truncated at 10. Hit@1 requires a relevant first source. Complete@k requires
**every** annotated supporting source, deduplicated by source identity.
Abstention cases are excluded and are not evaluated as answered questions.

| Arm | LongMemEval nDCG@10 | Hit@1 | Complete@5 | Complete@10 |
| --- | ---: | ---: | ---: | ---: |
| Historical BM25 (B0) | 0.923444 | 167/182 | 150/182 | 165/182 |
| Development-tuned BM25 (B1) | 0.926680 | 167/182 | 153/182 | 165/182 |
| Current ranking policy (B2) | 0.920647 | 165/182 | 150/182 | 165/182 |
| Dense only (B3) | 0.918289 | 162/182 | 162/182 | 172/182 |
| Sparse/dense RRF (B4) | 0.945967 | 167/182 | 162/182 | 175/182 |
| Equal score fusion (CC50) | 0.956496 | 172/182 | 164/182 | 175/182 |
| New local scorer (L) | 0.946893 | 171/182 | 156/182 | 172/182 |
| Pilot variant, 10 sources (P10) | 0.969596 | 181/182 | 163/182 | 165/182 |
| Exact prior GLM protocol (P10_prior) | 0.966885 | 180/182 | 163/182 | 165/182 |
| Same GLM on tuned BM25, 20 (BM20) | 0.957421 | 175/182 | 169/182 | 171/182 |
| New scorer plus GLM, 20 (M20) | **0.973263** | 174/182 | **178/182** | **180/182** |

| Arm | EverMemBench nDCG@10 | Hit@1 | Complete@5 | Complete@10 |
| --- | ---: | ---: | ---: | ---: |
| B0 | 0.463878 | 130/200 | 9/200 | 16/200 |
| B1 | 0.495336 | 143/200 | 12/200 | 17/200 |
| B2 | 0.459370 | 133/200 | 9/200 | 14/200 |
| B3 | 0.381420 | 103/200 | 7/200 | 14/200 |
| B4 | 0.442557 | 120/200 | 9/200 | 14/200 |
| CC50 | 0.509361 | 138/200 | 12/200 | 19/200 |
| L | 0.522768 | 141/200 | 11/200 | 22/200 |
| P10 variant | 0.510075 | 167/200 | 12/200 | 14/200 |
| P10_prior | 0.508451 | 166/200 | 11/200 | 14/200 |
| BM20 | 0.605235 | 174/200 | 16/200 | 19/200 |
| M20 | **0.615039** | 175/200 | 19/200 | 30/200 |

EverMemBench has only **five shared topics**, with 40 additional questions per
topic. These are new questions within development histories, not new-topic
generalization. The minimum two-sided exact group-sign p-value is 0.0625.
Do not treat the 200 questions as 200 independent histories. M20 versus B1
has a positive point difference (+0.119703) but corrected p=0.3125; it does
not pass the registered decision rule.

| LongMemEval comparison | nDCG difference | Nominal paired 95% CI | Holm p | All criteria |
| --- | ---: | --- | ---: | --- |
| L vs B1 | +0.020213 | [0.011012, 0.030925] | 0.000500 | Fail: complete@5 uncertainty |
| M20 vs B1 | +0.046583 | [0.021801, 0.072944] | 0.001600 | Pass |
| M20 vs pilot variant | +0.003667 | [-0.016988, 0.025266] | 1.000000 | Fail |
| M20 vs BM20 | +0.015842 | [-0.002855, 0.037473] | 0.397460 | Fail |
| M20 vs exact prior | +0.006378 | [-0.014596, 0.028442] | 1.000000 | Fail |

Paired effects, all five comparisons, guardrail checks, per-group results,
evidence recall at 5/10/20/50, precision, and original counts are included in
the replay JSON. The decision rule requires an absolute nDCG gain of at least
0.02, positive lower CI, Holm p below 0.05, and Hit@1/complete@5 lower bounds
no worse than -0.01. It was not relaxed after scoring.

## What changed, and what failed

The experimental local scorer combines whole-session BM25, passage BM25,
dense similarity and IDF-squared lexical scores. A regularized pairwise loss
fits bounded simplex weights with development-group balancing and a fixed
query-length gate. The implementation is provider-neutral and remains
outside the serving path. No new language model was trained.

All assisted arms use `accounts/fireworks/models/glm-5p3-flash`, temperature
0 and low reasoning. M20 and BM20 share 20-source candidate and 120,000-byte
evidence ceilings and a 2,048-token output allowance. This matched control is
essential: most of the supported benefit can be obtained by adding GLM to a
simple comparator; an additional benefit from the learned candidate ordering
was not statistically established. The prior protocol uses 10 sources and
1,536 output tokens, so comparisons with it also change context capacity.

Frozen feature-removal ablations were descriptive, not alternate finalists:

| Corpus | L | No whole BM25 | No passage | No dense | No IDF-squared | No gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| LongMemEval | .946893 | .949824 | .946893 | .930162 | **.963820** | .946893 |
| EverMemBench | .522768 | .518953 | .455349 | .500324 | **.529307** | .495239 |

Removing IDF-squared improved both final samples. Equal score fusion also
beat L on LongMemEval. These negative findings argue against deploying the
full learned scorer unchanged. No post-score ablation was promoted as a
confirmed replacement.

On the previously exposed NFCorpus official test (323 queries), nDCG@10 was
0.297560 for tuned BM25, 0.409802 for dense retrieval, 0.368249 for equal score
fusion and 0.343397 for L. This is exploratory transfer evidence using graded
gain `2**grade - 1`, and does not establish a general local-ranking advance.

## Historical comparisons and literary tests

July's published 46-case LongMemEval sample included three abstention cases.
After correcting eligibility, the same historical split has 43 answerable
questions: BM25 Hit@1 37/43, existing Thought Pins 38/43, new local scorer
41/43, and the earlier GLM pilot 43/43. The pilot's complete@5 was 40/43.
The original label "Recall@5/10=1.0" meant **any-evidence Hit@k**, not complete
support or answer accuracy. A different 46-question validation split must not
be confused with July's 46 total cases. These historical results are exposed
replays, not new independent evidence.

The first September study also stays on record: on its 200 EverMemBench
questions, historical BM25 nDCG@10 was .460499, the existing GLM pilot .502090,
and its new GLM/RRF finalist .483423. That study did not establish a local
algorithm win. Its [summary](artifacts/prior-study-summary.json) is preserved
as an archival result, rather than replaced by the follow-up's better figures.

Existing public-book tests, including the Sherlock Holmes salience fixture,
were checked as regression tests. Generated questions from the same literary
passages are not independently labeled external retrieval evidence. Personal
journals and private notes were not used in the study.

## Reliability, cost and limitations

- Strict whole-permutation validation retained every failure in the denominator:
  M20 28/382 fallbacks, BM20 32/382, pilot variant 5/382, exact prior 8/382.
  Each fallback preserves the original ordering once; there is no repair,
  partial merge, retry, or substitute provider.
- On 10 development repetitions, identical payloads kept the first result in
  8/10 cases and the full order in 3/10. Candidate-order permutations kept the
  first result in 9/10 and full order in 1/10. Live inference is not bit-repeatable.
- Fourteen separately state-labeled synthetic model fixtures achieved Hit@1
  and complete@5 of 14/14. They cover temporal changes, attribution, negation,
  multiple sources, instruction injection and other stressors; they do not
  estimate real-user accuracy or guarantee injection immunity.
- M20 truncated some source text on 191/382 questions; BM20 on 192/382.
  Source-ID completeness does not guarantee that every necessary fact was
  visible after truncation. Candidate ceilings and context ceilings differ.
- M20 mean inference cost was approximately $0.003935/query, median API latency
  3.739 seconds and p95 9.032 seconds. These are experimental external-call
  timings, not production end-to-end latency or a guaranteed current price.
- Follow-up provider usage cost was conservatively estimated at **$7.819**
  across 2,210 settled attempts, including new embeddings and development.
  Reused embeddings and earlier studies cost extra. No cache discount was
  assumed. [Costs](artifacts/costs.json) and [resources](artifacts/resources.json)
  preserve the measurement scope; no personal account balance is published.
- The study used pinned public corpora. Pretraining contamination is unknown.
  B2 is the current ranking policy on offline BM25-seeded source sessions,
  not the full production eight-channel retrieval system. Answer generation,
  abstention, live journals, infrastructure and device quality are separate tasks.

The strongest supported outcome is a benchmark-specific model-assisted
retrieval improvement over tuned BM25. Broader superiority, and the value of
the more elaborate local scorer over a simple matched model control, remain
unproven.
