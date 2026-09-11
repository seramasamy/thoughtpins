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

## iOS capture, authentication, and release verification

Capture cleared notes and links before persistence completed. It now clears only
accepted content and preserves any newer text entered during the request. Failed
offline storage returns an explicit failure; a successful offline result requires
a persisted draft. Journal and link submissions reject overlap, URL validation
rejects incomplete/non-web links, and Capture uses its parent's navigation stack
so its back button remains available.

Authentication snapshots and normalizes the account identifier while preserving
the exact password. A model-level guard prevents concurrent login/registration
and provider completions. The form keeps its mode and inputs stable while busy,
supports showing/hiding a password and dismissing the phone keyboard, and offers
a support-email fallback when a password-help email cannot open. The password
visibility icon retains its 44-point touch target at large text sizes.

Four native model tests and three iPhone SE UI workflows pass on iOS 17.2. They
cover failed disk writes, persisted offline notes, duplicate requests, invalid
input, 401/429 recovery, failed-link retry, back navigation, password visibility,
and registration/legal controls at accessibility5. Further device and final CI
results are recorded in the final verification section below.

The iOS CI change filter now compares the previous remote head with the entire
pushed tree. Five regression cases cover merge promotion, a multi-commit push,
fixture changes, a new branch, and documentation-only changes. CI runs the new
native model/UI cases and retains their XCTest attachments. Manual validation
no longer implies upload: App Store Connect upload requires the separate
`upload_testflight` input, which defaults to false.

Native verification exposed another export issue: SwiftPM's ignored `.build`
cache was included by the filesystem-based public export walker. Both hygiene
scanners now exclude that generated cache, with tests for nested Swift package
paths. This keeps compiled modules and local build paths out of public archives;
source scanning remains enabled. The obsolete Product-caption assertion was
updated to verify the real fictional-account captures on both homepages. A
current-WebKit Classic contrast failure prompted explicit theme ink on headings.

The broader repository check found 27 typing errors in existing test fixtures,
while the release gate only checked application code and scripts. The fixtures
now narrow optional results, use explicit side-effect helpers, and preserve the
same behavioral assertions. The full `mypy src scripts tests` command passes
across 452 files; CI and the strict release command now enforce that scope.

Local iPad Pro review also passes link recovery, landscape navigation, sign-in
recovery, and accessibility5 signup. Its keyboard disappearance is asynchronous;
the UI assertion now waits for the actual keyboard to close instead of sampling
it immediately after tapping Done. The normal and largest-text screenshots were
inspected, including the corrected password icon. The production iOS simulator
target builds for arm64 and x86_64. The modern homepage hero was reviewed last
and retained; the shared Product section supplies its visual improvement.
