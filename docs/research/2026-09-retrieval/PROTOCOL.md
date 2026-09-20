# Protocol and exposure record

This is an edited publication of the locally registered September 19 protocol,
with the pre-label baseline amendment described explicitly. Publication came
after evaluation; this was not an externally timestamped preregistration.
Original freeze/artifact digests are in `artifacts/provenance.json`.

Development used 196 LongMemEval training queries and 200 now-exposed
EverMemBench questions from the first September study. The old 46-answerable
validation and 43-answerable historical partitions were excluded from fitting.
Three LongMemEval evidence/history component folds and leave-one-topic-out
EverMemBench folds controlled local selection. An entire held-out topic was
excluded from its training fold.

Final evaluation used 182 previously unused answerable LongMemEval diagnostic
queries, excluding three overlapping history/evidence components, plus 200
previously unselected EverMemBench questions. Forty eligible questions per
topic were selected by SHA-256 of the canonical JSON string
`"20260920:" + query_id`, without filtering by performance. Same-topic final
questions do not establish new-topic generalization. All final labels were
sealed until 382 local and 1,528 model predictions existed. All final labels
are now exposed. The pre-scoring `final_labels_exposed: false` field in the
split snapshot is historical; `exposure.json` describes the completed state.

Historical BM25 kept k1=1.2, b=.75. Strong BM25 searched k1 in {.6,1.2,1.8}
and b in {.25,.5,.75,1}. Other families compared normalized sparse/dense
fusion, 256-token passage BM25 with stride 192, IDF powers {.5,1,1.5,2},
query-length-conditioned mixtures and regularized group-balanced pairwise
learning. The length gate is 64 distinct historical-tokenizer tokens. There
were 53 fixed-grid settings, 12 fitted configurations and eight validation
folds per fitted configuration. These are tuning trials, not 12 total fits.

An added family had to improve cross-fitted macro nDCG by .01, with no more
than .01 Hit@1 or complete@5 loss on either corpus. Simpler eligible methods
within .005 of the best nDCG were preferred. One local and one model-assisted
finalist were selected. Final ablations removed each feature or the query gate
without refitting, and were not eligible for post-score promotion.

Every arm preserved event/session source identity. Local candidates were
capped at 50; ceilings were measured at 10/20/50. Passage scores aggregated
to their original source by maximum. Missing inference metadata did not use
gold labels, answer IDs, question-type labels or reference windows as features.
The public judgments and diagnostic slices are exclusively evaluator inputs.
The current policy mutates candidates, so each comparator receives a fresh
clone; execution-order and duplicate-source invariants have separate tests.

M20 and BM20 shared model, prompt, output, candidate count and context ceilings.
The original P10 accidentally differed from the earlier study in deterministic
candidate shuffle and the missing-date header. This was discovered before new
final-label exposure. P10 was retained as a variant, and 382 exact P10_prior
calls were added; eight archived prior requests matched byte-for-byte. The
four-comparison family was expanded to five with Holm correction within each
corpus. No new finalist, prompt change or repeated tuning was introduced by
the amendment. Both old four-family and corrected five-family p-values are
retained; the five-family values govern the publication.

Primary ranking metric: binary-gain nDCG@10. Secondary metrics: Hit@1, MRR@10,
evidence recall, complete support at five/ten, and candidate coverage. All
failed model calls remain in the denominator with a single exact-order
fallback. No output repair, partial merge or fallback provider is allowed.
All final model calls returned a stop completion, although some JSON rankings
were invalid and used the fallback.

Uncertainty used paired cluster bootstrap with 10,000 draws, seed 20260920,
and query-weighted effects. Group-sign randomization was exact for five Ever
topics and Monte Carlo with plus-one correction for the 182 disjoint LME
groups. Its null assumes group sign exchangeability; the groups must represent
the claimed target population. Confidence intervals are nominal, not
simultaneous. Multiplicity is controlled by Holm within each corpus, not by
pretending all corpora form one independent mega-sample.

Promotion required at least .02 absolute nDCG improvement, positive lower CI,
corrected p below .05, and paired Hit@1/complete@5 lower bounds of at least
-.01. Negative or inconclusive comparisons stay negative or inconclusive.
The original first-study Ever result and previously exposed NFCorpus diagnostic
remain separately labeled. No post-score correction replaces a frozen outcome.
