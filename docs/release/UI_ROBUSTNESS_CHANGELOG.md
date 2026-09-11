# UI robustness changes

## Web chat recovery — 11 September 2026

Failed and rate-limited chat requests previously cleared the composer. Failed
edits also removed the visible conversation after the edited turn. Drafts now
remain recoverable, an explicit retry replaces the failed local turn, and a
rejected edit restores the original conversation and the edited draft. A newer
composer draft is preserved if it was typed while the request was pending.

The submission lifecycle is extracted into `useChatSubmission.ts`. It blocks
overlapping submissions, aborts on unmount, and keeps explicit cancellation
separate from retry. Restore conversation is disabled during a submission.
The message editor shares the main composer's keyboard handling so composing
text with an input method does not submit on Enter. Both enforce the same
50,000-character limit.

Validation: nine browser regression scenarios cover 429/503 recovery, newer
draft preservation, cancellation followed by another send, editing failure,
input-method composition, whitespace, and long/markup-containing content at
320 and 1440 pixels. Four scenarios failed before the fix; all nine pass after
it. The production build and 13 focused web contract tests pass. Static
contract checks now inspect both the view and its extracted submission owner.

Browser fixtures are fictional and local. No paid model request is needed for
these scenarios. Screenshots and execution logs belong in ignored `reports/`
directories and are not part of a public code export.

## Website accessibility — 11 September 2026

The footer home link lost its accessible name when its text was hidden at the
narrowest width. The seven supporting/classic pages now give that link an
explicit name. An audit of all eight pages at 320, 390, 834, and 1440 pixels
found seven link-name violations before the fix and none afterward; none of
the 32 layouts scroll horizontally. Reduced motion is enabled for the audit.

To reproduce, serve `site/` on loopback port 8878, then run
`node scripts/audit-site-accessibility.mjs` from `frontend/`. The script uses
Playwright Chromium and saves screenshots and axe results under ignored
`reports/ui-robustness/`. `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` can select an
installed Chrome when the host cannot run Playwright's bundled browser.
