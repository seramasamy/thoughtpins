# Dataset attribution and licenses

Only identifiers, source-level judgments, derived numeric features and
experimental predictions are redistributed. Raw conversations, questions,
answers, document text and literary passages are not included in this bundle.
The software's Apache-2.0 license does not override third-party data licenses.

| Source | Exact identity used | License and credit |
| --- | --- | --- |
| [LongMemEval-cleaned S](https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned) | SHA-256 `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442` | MIT; Di Wu and LongMemEval contributors; [included notice](licenses/LongMemEval-MIT.txt) |
| [EverMemBench-Dynamic](https://huggingface.co/datasets/EverMind-AI/EverMemBench-Dynamic/tree/a6b210a32248e841967b7b64a64281d2ff3f669d) | revision `a6b210a32248e841967b7b64a64281d2ff3f669d` | Apache-2.0 as declared by publisher EverMind-AI at that revision; [license text](../../../LICENSE) |
| [NFCorpus, BEIR distribution](https://huggingface.co/datasets/BeIR/nfcorpus) | official 323-query test split; archive SHA-256 `efe5be03f8c5b86a5870102d0599d227c8c6e2484328e68c6522560385671b0b` | CC BY-SA 4.0; Vera Boteva, Demian Gholipour, Artem Sokolov and Stefan Riezler; BEIR distribution by Nandan Thakur and contributors; [license terms](https://creativecommons.org/licenses/by-sa/4.0/legalcode.en) |

File-specific download digests, the Ever pinned dataset-card digest and the
original public URLs are in [datasets.json](artifacts/datasets.json). The LME
download URL uses `main`, but the required content digest is fixed; a different
digest is a different dataset and must fail verification. Do not silently
substitute another release or a similarly named dataset.

The `nfcorpus.jsonl` judgments and derived experiment data, and
`nfcorpus-expected.json`, are supplied under CC BY-SA 4.0. Changes comprise
selection of official test IDs, projection of source-level grades and addition
of experimental rankings. The LME-derived portions of other files retain the
included MIT notice; Ever-derived portions retain Apache-2.0 terms. Original
Thought Pins code, reports and experiment metadata use the repository license.
No upstream author endorses these results.

LME retrieval units are whole conversation sessions, including source dates
and role-attributed turns. Source identities preserve event identity rather
than collapsing different sessions with matching text. Three abstentions in
the July split are removed from answerable retrieval metrics.

Ever retrieval units are a topic/date/group dialogue block. Gold message
references are resolved by explicit message index, never list position, then
projected to their containing source. The adapter validates reference dates,
groups and message membership independently. The pinned release supplies no
legitimate query as-of date, so the full topic history is used; evaluator
reference windows are not inference filters. Multiple-choice options, where
present, are observable question input; the answer field is excluded.

NFCorpus uses each document's title plus body as a source. Its graded labels
keep exponential gain `2**grade - 1`; the memory tasks use binary gain. This
transfer split was already exposed and is labeled exploratory throughout.

Sherlock Holmes/public-book fixtures remain separate regression tests. No
novel corpus, private journals, personal notes or LoCoMo data was substituted
for these frozen external evaluation sets.
