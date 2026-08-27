# Submission status — Thought Pins 1.0.0 (build 1)

**Date:** 2026-08-26
**Verdict: ready to submit once the developer account exists**, with the
device-only work in `docs/release/IOS_26_DEVICE_RISKS.md` done on the first
build that reaches hardware.

This file says what is finished, how each thing was actually checked, and what
is still open. "Verified" here means a command was run and its output read —
not that the code looks right. Anything checked only by reading is labelled as
such.

---

## The submission plan, item by item

| Item | State | How it was checked |
|---|---|---|
| P0.1 Invite gate cannot depend on a Railway variable | **Done** | `INVITE_ONLY` deleted entirely from a scratch environment: register returned 200 and `invites/status` returned `{"invite_required": false, "admitted": true}`. 8 tests in `tests/test_invite_gate_default.py` fail if the default returns to `True` |
| P0.2 Memory cards and library sources open | **Done (option A)** | Both detail screens open against production with real content and no internal ranking fields on screen |
| P1.3 Markdown blocks render | **Done** | 11 parser tests in `ThoughtPinsCore`, plus a rendered-screen test asserting no stray `#`, `>`, `-`, `` ``` ``, `---` or `**` anywhere on the reply screen |
| P1.4 Errors stop auto-dismissing | **Done** | Error banner still on screen after 11 seconds and dismissible; success banner gone after 8 |
| P1.5 Strings speak English, not schema | **Done** | Sweep of every literal in the app package; every remaining snake_case string is a wire value being matched or a comment |
| P2.6 Denied microphone | **Open by design** | Cannot be faked — `simctl privacy revoke microphone` does not take. Written up as a device test |
| P2.7 Age rating | **Confirmed** | Every premise in `AGE_RATING.md` re-checked against the build. Mature tier stands |
| P3.8 Clean rehearsal from nothing | **Done** | Wiped simulator, self-registered a brand-new account against production, first run, every feature, screenshots recaptured |
| P3.9 This file | **Done** | — |
| P3.10 Full gate and archive | See "Gates" below | — |

---

## What was verified against production, not a stub

On a wiped simulator, against `api.thoughtpins.com`:

- **Self-registration end to end.** A brand-new address registered, hit the AI
  processing consent screen (not an invite wall), reached the app, saved a
  first note, and got a chat reply. This is the path a reviewer takes when they
  ignore the demo credentials, and it is the one that used to be one unset
  environment variable away from failing.
- **Every feature, in one pass:** chat reply, private-memories toggle, recap in
  day/week/month, memory card detail, places, library source detail, link
  import ("Reading saved."), capture, response voice, importance prompts, and
  account export ("Your export is ready.").
- **Account screen reachable** — export, delete account, privacy policy, terms,
  and support are all on it. Guideline 5.1.1(v) depends on that button not
  being covered, which is what the banner work was about.
- **In-app reporting** on a chat reply, posting to `/v1/safety/reports`.

Screenshots in `screenshots/iphone-1284x2778/` were recaptured from this run.
The previous chat screenshot showed the Markdown bug and has been replaced.

---

## Two defects this pass found and fixed

Worth recording, because both were introduced by the work itself and both were
caught by an acceptance test rather than by reading the code.

1. **`showSuccess` called itself.** A bulk edit that rewrote 70 banner call
   sites also rewrote the assignment inside the new helper, so the helper
   recursed. The app died on the first banner it ever showed — including
   "Signed in." — which meant sign-in appeared to work and then the process
   vanished. No crash report was written, which is why it read at first as a
   test-harness fault.
2. **A feature sweep gone blind.** Splitting the banner in two left the sweep
   reading only the success identifier, so every error came back as
   "(no banner)". It also slept 25 seconds before reading a banner that now
   clears in 4. Both fixed; the sweep reports real results again.

---

## Open, and why

- **Denied microphone.** Device-only. Steps are in
  `docs/release/IOS_26_DEVICE_RISKS.md`. The denied branch exists and is
  correct by reading, and has never executed.
- **Sign in with Apple.** Cannot be exercised until the capability is on the App
  ID. `com.apple.developer.applesignin` stays in the entitlements.
- **Google sign-in.** Suppressed by design until Apple sign-in exists
  (Guideline 4.8). `GoogleOAuthTokenProvider.swift` compiles only on CI, where
  the toolchain can resolve GoogleSignIn 9.1.0; this Mac runs Swift 5.9.2 and
  cannot.
- **iOS 26 on an iPhone 17 Pro Max** is where this app runs for the first time
  on real hardware. The appearance risks are listed in the device risks file.

---

## Gates

- Python: `pytest`, `ruff check`, `ruff format --check` clean.
- `scripts/check_architecture_budget.py` passes. Three files were pushed over
  their size budget by this work and the new behaviour was extracted rather
  than the budget raised: `config_admission.py`, `ThoughtPinsMessages.swift`,
  `ThoughtPinsDetailScreens.swift`, `ThoughtPinsReplyView.swift`.
- `scripts/check_ios_submission_source.py` passes.
- `ThoughtPinsCore`: 49 tests, 0 failures, in the iOS Simulator.
- mypy reports 24 pre-existing errors in 9 files, none in anything this work
  touched. Unchanged from `HEAD` before this pass.

## The review pass after this one (T0-T3)

A second review found that the two detail screens had been written after every
pass the rest of the app had, and had had none of them. They have now had all
of them, and three items were real:

| Item | Result |
|---|---|
| T0.1 iPad readable column | The detail screens had it; the **Form drew its own backdrop behind it**, so the column sat in a band with hard edges. Fixed. Four other screens -- Recap, Capture, Pins, **Account** -- had never had the column at all; Account is the 5.1.1(v) screen and its Toggle stranded its switch an inch and a half from its label. All five fixed |
| T0.2 Dynamic Type AX5 | No truncation, no collision, nothing outside the screen, on both screens |
| T0.3 VoiceOver | Section headers announced in visual order; every element labelled; rows combined so a row is one utterance rather than a bare date; back affordance announces "People" / "Pins" |
| T0.4 Light and dark | Both clean |
| T0.5 375pt | Clean on an iPhone SE |
| T0.6 Empty state | **Was a blank screen** below the header. Now explains itself. Verified with an injected empty payload |
| T0.7 Offline | Resolves within the 30s request timeout, says what happened, and the reading detail keeps its cached copy and says so. Verified with a dropped connection |
| T0.8 Errors | **Both screens blamed the connection for everything.** `ThoughtPinsLoadFailure` now distinguishes offline, timeout, gone, server fault and signed-out, and hides the retry where retrying cannot work. Verified against injected 404 and 500 |
| T0.9 Affordance | Rows are `NavigationLink`s inside a `List`, so they carry a disclosure chevron and report as buttons |
| T0.10 Content vs promise | **The promise is not quite met -- see below** |

Errors and offline were verified with a local HTTPS proxy that forwards to
production and injects a chosen fault on the two detail endpoints only. Nothing
about the failure paths is reasoned about.

## CI, on this commit

Run `33025204863` on `009ca14`, **on an ordinary push to main**, all seven jobs
green. That is new: the `ios` job used to run only on a tag or a manual
dispatch, so every green check on main excluded iOS. It now runs whenever a
push to main touches iOS, decided by a seconds-long Linux job.

The build number in that run was **135** -- the commit count -- not `1`. It had
been pinned, so the first TestFlight upload would have worked and the second
would have been rejected as a repeat build number. The archive and its dSYMs
are kept for 30 days (4.8 MB), so a failed submission is retryable without a
rebuild at 10x billing. The four signing and upload steps are authored and
skipped until the secrets exist.

Previous run `32943286763` on `2ed3d2d`, six jobs green:

| Job | Result |
|---|---|
| `python` | success |
| `postgres` | success |
| `web` | success |
| `container` | success |
| `android` | success |
| **`ios`** | **success** — XcodeGen, shared Swift package tests, unsigned simulator build, **unsigned archive**, archive contains the app, Info.plist checked |

The `ios` job is the one that matters here: it is the only place
`GoogleOAuthTokenProvider.swift` compiles, because GoogleSignIn 9.1.0 declares
`swift-tools-version:6.0` and this Mac runs Swift 5.9.2.

The three steps that fail locally (SBOM, approval tilt, frontend audit) all
pass in the `web` and `python` jobs, which have Node.

## Two things that need your decision

**The description sentence about people.** It says "Open a person and see what
you have said about them and **when you last spoke**." The detail screen shows a
section headed *Last mentioned*, and the server field behind it is `last_seen` --
the date the person was last **referenced in your journal**, not the date you
last spoke to them. On the review account it reads 2026-08-25 because that is
when the entry was written. Those are different claims, and nothing in the app
records a conversation date. No field was added to make the copy true. Either
change the sentence to "when you last wrote about them", or accept that "last
spoke" is loose. Recommendation: change the sentence.

**GoogleSignIn.** See the recommendation in the session report; nothing has been
changed.

## A note on the simulator UI tests

The tests that produced the evidence above live outside this repository, in a
scratch build that references the repo's Swift package by path. They are **not**
committed, because they carry the review account's password inline and
`AGENTS.md` keeps credentials out of source control. They are a local
verification harness, not a CI gate; CI covers the archive, not the simulator.
