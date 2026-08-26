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

## A note on the simulator UI tests

The tests that produced the evidence above live outside this repository, in a
scratch build that references the repo's Swift package by path. They are **not**
committed, because they carry the review account's password inline and
`AGENTS.md` keeps credentials out of source control. They are a local
verification harness, not a CI gate; CI covers the archive, not the simulator.
