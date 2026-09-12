# Contextual Salience

Thought Pins keeps explicit user importance separate from inferred salience. A
five-star rating is a strong preference signal, but it does not replace exact
retrieval evidence or silently turn a peripheral fact into a core identity.

## Model

`thoughtpins.memory.salience` implements `salience-v4` as a bounded, weighted
evidence model:

- recurrence across distinct entries, using a saturating curve rather than raw
  frequency;
- structural role, where direct subject facts and agency outweigh passive
  co-occurrence;
- graph breadth, actual extracted-topic diversity, and normalized topic
  entropy;
- temporal persistence and source diversity, which distinguish a durable
  pattern from a burst of repeated mentions in one note;
- observed, reported, and inferred evidence quality;
- a slow recency prior that does not erase old memories;
- explicit five-star feedback as a bounded manual prior;
- attributed statements, causal links, unresolved threads, and high-stakes
  scenes as a bounded narrative-structure signal;
- uncertainty that falls as independent evidence accumulates.

The weight maps are named constants whose coefficients sum to one, and every
score records the exact per-signal contribution. The uncertainty diagnostic
uses the normalized spread of a symmetric Beta posterior over an effective
sample size. Effective evidence rewards distinct entries, active days, source
diversity, and structural support while logarithmically capping duplicate
mentions. This prevents a name repeated many times in one note from looking as
well-supported as a pattern observed independently across weeks. The value is
explicitly epistemic: it is not presented as the probability that a memory is
true.

Normalized signals are persisted with every entity score. This makes an
ordering explainable during debugging without presenting a probabilistic score
to users as objective truth. Changing, clearing, or undoing a star rating and
deleting an entry immediately refreshes every affected memory card.

The entry score also records scene analysis, topics, entry type, and the
durable structures extracted from the note. Search uses the score only as a
small prior after lexical, vector, graph, phrase, provenance, and
query-conditioned scene signals have been fused. During social queries, star
importance is gated by the candidate's coverage of the requested facets.
Exact evidence remains dominant.

## Literary calibration

The offline fixture in `tests/fixtures/literary_salience_corpus.json` uses the
public-domain Sherlock Holmes series as a structural calibration set. It tests
the distinction between recurring protagonists, narrators, recurring allies,
case-specific high-agency characters, and one-off participants. The texts are
not copied into the product or used as user data. Source links are retained in
the fixture for provenance:

- Project Gutenberg: `A Study in Scarlet`, eBook 244
- Project Gutenberg: `The Sign of the Four`, eBook 2097
- Project Gutenberg: `The Adventures of Sherlock Holmes`, eBook 1661
- Project Gutenberg: `The Return of Sherlock Holmes`, eBook 221

The fixture encodes intended ordering for recurring participants, direct
involvement and themes across entries. Whether these signals produce useful
ordering in personal journals requires evaluation on that workload.

The fixture is an invariant suite rather than a learned model. It checks that
structural role can beat raw name frequency, recurring themes beat vivid
one-offs, duplicate mentions do not masquerade as independent evidence, manual
ratings remain bounded and monotonic, weighted contributions reconcile to the
stored score, and uncertainty falls as independent evidence accumulates.

The reproducible corpus runner in
`scripts/evaluate_public_domain_social_corpus.py` uses the official Project
Gutenberg offline catalog, validates item headers, and caches texts only under
ignored `.tmp/` storage. It never inserts literary text into a user's database
or vault.

## Operations

New completed entries score themselves during ingestion. Existing databases can
be backfilled safely with:

```powershell
python scripts/recompute_salience.py
```

Use `--user-id` to scope a backfill to one tenant. Scores carry a model version
so a future formula can be recalculated without pretending old values were
produced by the new model.
