# Product presentation and native release review

## Website and repository presentation — 11 September 2026

The Product section on both homepages now pairs actual, fictional-account web
captures with a three-step capture, connection, and recall example. The shared
layout adapts from 320 to 1920 pixels. Device tabs support arrow/Home/End keys,
preserve an explicit choice when resizing, and leave a useful static preview
when JavaScript is disabled. The Classic site adds editorial typography,
clearer navigation, refined surfaces, and consistent light/dark styling.

Validation: 19 Chromium and 19 WebKit scenarios pass across eight widths. They
check preview loading, overflow, keyboard navigation, resizing, no-JavaScript
fallback, appearance persistence and WCAG A/AA axe checks. Local WebKit 18.4
uses an isolated compatible test driver because this Mac runs macOS 13; CI
uses the repository's current Playwright dependency. Screenshots and raw logs
remain under ignored `reports/release-polish/` and `.tmp/release-polish/`.
The cache key and digest cover all 28 versioned assets.

The public README now has a code-native brand banner, current CI badge,
product capture, architecture map, and direct reviewer paths. The algorithm
guide documents all eight available retrieval paths, reciprocal rank fusion,
the actual clipped ranking equation, 20 policy parameters, diversity and
coverage selection, and evidence packaging. Historical results distinguish
candidate retrieval, fixed-pool reranking, and answer quality. Unsupported
self-ratings and state-of-the-art implications were removed; the 46-case
LongMemEval result remains explicitly a small confirmatory reranking study.

The earlier redesign was promoted to the default GitHub branch in commit
`20cdfe6`. Its Python, web, PostgreSQL, Android, and container CI jobs passed in
[run 34631279642](https://github.com/seramasamy/thoughtpins/actions/runs/34631279642).
That run skipped iOS because the previous change filter compared only the
merge's first parent, whose tree was already identical. Native evidence must
be assessed from the subsequent native verification, not inferred from that
green workflow.

No model-provider calls or real account data are used by these review fixtures.
