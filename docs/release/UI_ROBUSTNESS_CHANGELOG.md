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

## Web saves and offline recovery — 11 September 2026

Journal and pin saves now reject overlapping submissions, including two form
events before a render. Completion clears only the submitted draft, preserving
new text typed during the request. A local-storage failure keeps journal text
editable and explains that it still needs saving. A successful chat retry
clears the previous error without adding a success toast to each reply.

Six saving scenarios pass: duplicate journal/pin submissions, newer-text
preservation, failed pin retry, exact account-deletion confirmation and failed
deletion recovery, encrypted offline drafts surviving reload, and storage
exhaustion. The two original save-lock scenarios failed before the fix. Chat
429/503 recovery was rerun after the notice change and passes.

## Website cache consistency — 11 September 2026

The release gate found two cache versions in use across the redesigned site.
All versioned references now use `20260911-robustness-1`, and the recorded
digest covers all 26 referenced assets. Returning visitors can receive the
updated styles, fonts, previews, and manifest together. The cache gate passes.

## iOS chat recovery and keyboard access — 11 September 2026

Chat submission now returns its own success result instead of having the view
infer it from the current banner. Failed sends restore the submitted text and
the preceding question/reply pairing; successful retries retain the new
question and clear the earlier error. The model rejects overlapping chat
requests. This behavior lives in a focused submission module. A Done control
lets people dismiss the keyboard while keeping an unsent draft.

Validation includes all 78 native core tests, plus simulator cases for 503 and
429 recovery followed by success, whitespace, keyboard dismissal, empty-search
recovery, cancelling the voice disclosure, and the largest Dynamic Type size
across all five tabs. Export was opened in the system share sheet and its JSON
file checked for the expected fictional account/table payload. Cancelling
account deletion leaves the account screen open. The initial export test
mistook an iOS activity row for a button; the corrected test passes.
