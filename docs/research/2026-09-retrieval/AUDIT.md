# Accuracy audit of the frozen retrieval backtest

On September 20, 2026, three checks confirmed the published numerical result:
the original offline replay, a separate implementation of the metrics and
statistics, and a read-only audit of the original public-data experiment
files. The audited snapshot was `be3275856dffa4224387a8f6c354a6d9f1a219ba`,
merged into `main` at `cda4f3b86b0a56fab57f3cc301abffb8b47ccd1e` with an
identical source tree. No frozen configuration, prediction, label or reported
score was changed. This is a verification of existing results, not a new
holdout, optimization trial or paid model run.

## What was checked

| Check | Evidence and outcome |
| --- | --- |
| Published replay | Verified 41 source/artifact hashes, refitted weights from 396 development queries, reconstructed 4,584 local numeric rankings, and reproduced primary, historical and transfer tables, robustness decisions and costs. |
| Independent arithmetic | A separate script imports no Thought Pins code. It recalculated all 17 final arms on both memory corpora, including binary nDCG@10, MRR@10, recall and complete support. All means agree within 1e-12. |
| Independent uncertainty | Reimplemented paired cluster bootstrap, group-sign randomization and five-comparison Holm correction. All 30 paired metric comparisons reproduce the reported effects, intervals and p-values within 1e-12. |
| Model accounting | Independently validated all 1,528 final model decisions. Invalid permutations retain the exact original order; all 73 fallbacks remain in their denominators: M20 28, BM20 32, P10 variant 5, exact prior 8. |
| Raw dataset and labels | Rechecked the LongMemEval content digest and all ten pinned EverMemBench dialogue/QA file digests. All 382 published relevance judgments match the raw evaluator labels. |
| Source identity and exposure | Reconstructed all 8,654 LME source occurrences and 6,011 referenced Ever message indices. Rechecked the three shared-evidence/history exclusions and the deterministic 40-question selection within each Ever topic. Final query IDs do not overlap development IDs. |
| Raw inference inputs | All 1,528 original request hashes and response projections match the published records. Candidate text, source dates and fixed truncation match the source records; question inputs contain the question and its declared date header, with no gold answer, relevance flag, reference window or evaluator question type added. |
| Freeze preservation | All 301 original source/configuration freeze entries, including the prior-control amendment, still match their hashes. |

The raw audit used locally retained, ignored public-corpus files and full
request/response archives. They were read without making network or model
calls. Those full archives are not redistributed; the public replay is
cached-feature computational replication. Local hash consistency does not
independently prove the chronology of preregistration or rule out a model's
pretraining exposure. These limitations remain unchanged.

The raw LongMemEval corpus contains 13 cases with repeated distractor session
IDs, and no repeated answer-session IDs. The projection preserves distinct
dated/content event identities. Repeated distractors did not create duplicate
gold evidence or change the final denominators.

## What the gain actually means

All three rows below use the same 182 final LongMemEval questions.

| Method | nDCG@10 | Hit@1 | Complete@5 | Complete@10 |
| --- | ---: | ---: | ---: | ---: |
| Tuned BM25 | 0.926680 | 167/182 | 153/182 | 165/182 |
| Exact previous GLM protocol | 0.966885 | 180/182 | 163/182 | 165/182 |
| New local scorer plus GLM | 0.973263 | 174/182 | 178/182 | 180/182 |

Against tuned BM25, the nDCG difference is **+0.046583**, approximately **5.0%
relative**. The nominal paired 95% interval is [0.021801, 0.072944], and the
five-comparison Holm p-value is 0.001600. Complete@5 rises by **25 questions**,
or **13.74 percentage points**, from 84.07% to 97.80%. The numerical Hit@1 gain
is seven questions; its separate uncertainty does not establish a positive
Hit@1 effect. The registered noninferiority guardrail is satisfied.

| New scorer plus GLM versus tuned BM25 | Improved | Worsened | Tied |
| --- | ---: | ---: | ---: |
| Per-question nDCG@10 | 42 | 16 | 124 |
| Relevant first source | 13 | 6 | 163 |
| All supporting sources within five | 26 | 1 | 155 |

The direction of the prior-model comparison is different. Relative to the
exact previous GLM protocol, complete@5 gains 16 cases and loses one, while
Hit@1 gains two and loses eight. A method can recover more of the evidence
within five sources while putting a less useful source first. Its overall
nDCG advantage over that prior protocol is not established: +0.006378,
95% interval [-0.014596, 0.028442], Holm p=1.0. It is not a confirmed new best
model or a win over the last GLM test.

## Why high nDCG and incomplete evidence can coexist

Binary nDCG@10 discounts each relevant source by `1/log2(rank + 1)` and divides
by the best possible discounted ordering of the annotated relevant sources.
It is not the percentage of questions answered correctly. Hit@1 tests only
the first source. Complete@k requires every annotated supporting source.

For example, with two gold sources, an irrelevant first result followed by
both gold sources has Hit@1=0 but Complete@5=1. Neither metric is inconsistent
with the other. Session-level complete support also does not prove that a
truncated model context contained every needed sentence.

The LongMemEval sample searches **38-62 supplied sessions per question**
(median 47). It does not search every source in a shared global archive.
There are 58 questions with one supporting source, 92 with two, 14 with three,
eight each with four and five, and two with six. Consequently, even an oracle
could complete only 180/182 questions within five results. The observed
178/182 remains below that ceiling. The [upstream task definition](https://github.com/xiaowu0162/LongMemEval#-dataset-format)
distinguishes session retrieval labels from generated-answer evaluation.

EverMemBench searches **688-723 date/group blocks per question** (median 721).
Of its 200 final questions, 113 require more than five supporting blocks, so
Complete@5 cannot exceed 87/200 even with perfect ranking. The actual 19/200
does not approach that ceiling. This explains part of the difference between
the corpora without changing any denominator. There are only five shared
topics, so a positive point estimate and bootstrap interval do not overcome
the exact group-sign test's minimum two-sided p-value of 0.0625. No confirmed
EverMemBench superiority claim is warranted.

## Recheck the public arithmetic

With Python 3.13, from the repository root:

```bash
python -m pip install -r docs/research/2026-09-retrieval/replay-requirements.txt
python scripts/replay_retrieval_study.py --output reports/retrieval-study-replay.json
python scripts/audit_retrieval_metrics.py --output reports/retrieval-metric-audit.json
```

The first command after installation verifies the frozen manifest and refit.
The second independently recomputes metrics, model decisions and statistical
comparisons from public IDs and numeric results; expected values are used only
for checking. It also reports per-question improved/worsened/tied counts and
gold support-size distributions. Neither evaluation command calls a provider.

[Hand-worked tests](../../../tests/test_retrieval_metric_audit.py) check the
distinction between first-hit, partial recall and complete support, binary
versus graded gain, duplicate/empty-gold rejection, exact-order fallback and
group-level randomization. The original replay and independent audit run in
the Windows/Ubuntu research workflow. Dataset mappings are described in
[DATASETS.md](DATASETS.md); the unchanged limitations and all comparison arms
remain in the [full report](README.md).
