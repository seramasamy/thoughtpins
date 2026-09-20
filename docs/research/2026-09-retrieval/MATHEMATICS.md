# Fitted objective and checked properties

For fixed features x in [0,1]^4, score a source with w^T x, where w belongs
to the probability simplex. With the fixed query gate, two separate
four-dimensional simplex blocks handle at most 64 and more than 64 distinct
query tokens. Source identity and the feature construction do not use labels.

For each development query, pair every annotated positive with up to eight
BM25-selected hard negatives fixed before fitting. Each query contributes
total weight one within its training group. For pair difference d and
nonnegative normalized row weights a, the group loss is

```text
L_g(w) = sum_i a_gi log(1 + exp(-w^T d_gi))
J(w) = tau log(sum_g p_g exp(L_g(w)/tau))
       + lambda/2 ||w - w_BM25||^2
gradient L_g = -sum_i a_gi sigmoid(-w^T d_gi) d_gi
gradient J = sum_g softmax(log p_g + L_g/tau) gradient L_g
             + lambda (w - w_BM25)
```

The selected fit used lambda=.01, tau=1, analytic-gradient SLSQP, and a BM25
simplex prior. Half the prior risk mass belongs to LongMemEval and half is
distributed across the available Ever topics. Group identities enter training
loss balancing only; the serving-style score accepts no corpus/topic label.
The chosen weights are recorded without rounding in `artifacts/config.json`.

Fixed-feature logistic loss is convex. Log-sum-exp is convex and coordinatewise
nondecreasing, so its composition with the group losses is convex. Positive
L2 regularization makes this objective strongly convex on the convex feasible
simplex product. The fixed gate preserves joint convexity. This gives a unique
minimizer of this surrogate problem, not a theorem about nDCG, real-world
memory, temporal reasoning, or generalization. Group robustness depends on the
chosen development groups and their prior masses.

Whole-source BM25 uses the historical tokenizer. Passage BM25 uses fixed
256-token windows, stride 192, deduplicates identical windows within an event,
and takes the maximum per original source. Other features are dense cosine
and BM25 with squared IDF. Query-local normalization is

```text
(s - min(0, min(s))) / (max(0, max(s)) - min(0, min(s)))
```

A zero range gives neutral zeros. The dense representation came from the
pretrained Qwen3 embedding model; its benefit is not credited to new local
mathematics. Whole BM25/dense equal fusion is an explicit simpler control.

Centered finite differences independently check gradients. Synthetic known
solutions, simplex feasibility, stable candidate identity, score normalization,
empty sources and permutation equivariance have focused tests. The original
fit's finite-difference Hessian minimum eigenvalue was .0104935 and its KKT
residual was below 1.9e-9. These local numerical diagnostics do not validate
the empirical choice of features; the final ablations showed IDF-squared hurt.

The first study also implemented a fixed nonnegative facet-coverage objective
with diminishing returns. Its cardinality greedy guarantee does not extend
automatically to token-cost heuristics, arbitrary redundancy penalties or
changing facet scores. It did not become the follow-up finalist. Retaining
that implementation and its tiny-instance tests makes the rejected direction
inspectable without implying an empirical win or new mathematical theory.

The research reasoning model proposed hypotheses and critiques. Its incorrect
gradient-sign and nonuniqueness suggestions were rejected by the independent
derivation and numerical tests. Evaluated models were not the sole authority
for external gold labels.
