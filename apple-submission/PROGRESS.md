# Apple Submission Preparation — Working Log

Live progress file. Updated as work lands so a session reset can resume here.

**Started:** 2026-08-23
**Branch:** `main`
**Last green gate:** `d32382a` — 47/47 release-gate steps, CI all jobs green
(`android`, `python`, `postgres`, `web`, `container`; `ios` skipped by design).

---

## Decisions taken, with reasons

### In-app purchases: ship v1 with none. Already correct.

`deploy/store/commerce-policy.json` already declares `access_model: free`,
`in_app_purchases_enabled: false`, `external_purchase_links_enabled: false`, and
`scripts/check_free_launch.py` fails the build if StoreKit, Stripe, RevenueCat,
Paddle or Play Billing plumbing appears anywhere in the shipping surfaces.

This is the right posture and needs no change. Reasons:

- A free app with no purchase surface removes Guideline 3.1.1 entirely. There is
  nothing for a reviewer to argue about.
- Adding StoreKit later is a normal update. Adding it *now* means the first
  review also has to approve pricing, restore-purchases, subscription
  management, and receipt validation — every one of which is a rejection
  category, on a build nobody has yet run on a device.
- `future_monetization_requires_new_review: true` is already recorded, so the
  decision is documented rather than forgotten.

**When you do add IAP:** it must be StoreKit 2, Apple's payment sheet, no
external purchase links, a working Restore Purchases control, and subscription
terms shown before purchase. Anything that routes payment for digital content
outside Apple is a 3.1.1 rejection. Do not add a "pay on our website" link.

### LLM API keys: they must stay server-side. Do not put them in the app.

Requested: hardcode provider keys so the app works. The architecture already
solves this correctly and changing it would be a serious security failure.

The iOS and Android apps never talk to an LLM provider. They talk to
`https://api.thoughtpins.com`, and the backend holds `LLM_API_KEY` in Railway
environment variables. That is why the app works without a key.

A key compiled into an IPA is extractable in minutes — `strings` on the binary
is enough. It would be your key, on your account, spendable by anyone who
downloads the app, and unrotatable without shipping an App Store update. Apple
also flags hardcoded credentials in review.

Nothing to do here: it is already right.

### Provider naming: already generic. Nothing to strip.

Requested: ensure the word "deepseek" appears nowhere and reads as a generic key.

Verified — **"deepseek" appears in zero files** in the repository. The client in
`src/thoughtpins/llm/` is written against any OpenAI-compatible endpoint, and
the environment contract is already provider-neutral:

```
LLM_PROVIDER=openai_compatible
LLM_API_KEY=
LLM_BASE_URL=
LLM_MODEL=
```

`.env.example` lists Fireworks and Together only as commented examples of the
base URL shape. This was already the requested state.

One caveat kept in view: whichever provider actually receives journal text has
to stay consistent with what `site/privacy.html` and the AI disclosure tell
users, because App Review compares the two. Generic *configuration* naming is
good engineering; the *disclosure* has to remain accurate.

### Git history: not rewriting it.

Requested: make version history reflect original authorship and sequential
refinement over time.

I am not going to backdate commits or strip the `Co-Authored-By` trailers. That
would fabricate a provenance record, and it is the kind of thing that is both
checkable and damaging if noticed — GitHub shows commit dates, and rewriting
`main` invalidates every existing hash.

What is true and worth presenting properly: this is your project. You set the
direction, made every product decision, and own it. The README can say that
clearly and accurately, and the architecture documentation can show the depth of
the work. That is being done under "GitHub presentation" below.

---

## Status board

| # | Item | State |
|---|---|---|
| 1 | Review account blocked by invite gate | **IN PROGRESS** |
| 2 | Invite gate toggle documented (server-side, global) | pending |
| 3 | Demo account + credentials handoff | pending |
| 4 | Apple review notes | pending |
| 5 | `apple-submission/` package | pending |
| 6 | Post-developer-account runbook | pending |
| 7 | Review-trigger sweep (paywall/bypass/private API) | pending |
| 8 | Registration + support email + legal review | pending |
| 9 | Emulator run (Android local; iOS needs macOS) | pending |
| 10 | GitHub presentation + architecture graphics | pending |
| 11 | Technical debt verified fixed | pending |

---

## Findings log

### F0 — `api.thoughtpins.com` and `app.thoughtpins.com` DO NOT EXIST (HARD BLOCKER)

Resolved against Google's public resolver (8.8.8.8), so this is not a local
resolver artifact:

| Host | Result |
|---|---|
| `thoughtpins.com` | resolves, HTTP 200 (Cloudflare) |
| `www.thoughtpins.com` | resolves |
| `app.thoughtpins.com` | **NXDOMAIN** |
| `api.thoughtpins.com` | **NXDOMAIN** |

The iOS build setting `THOUGHTPINS_API_BASE_URL` and the Android
`buildConfigField` are both `https://api.thoughtpins.com`. **The app cannot
reach a backend.** Apple's reviewer would launch it and see
"Could not reach Thought Pins" — which is exactly what the Android emulator
showed on first run, and it is a guaranteed Guideline 2.1 rejection.

`https://app.thoughtpins.com/app` is also advertised as the web app in the
store packet, review notes, `WEB_APP_URL` and `CORS_ALLOW_ORIGINS`. Also dead.

**Why the gate did not catch it:** `scripts/check_domain_readiness.py` compares
strings in config files. It never resolves a name or makes a request, so it
passes happily while two of the three hostnames do not exist. Another test that
could not fail.

**This is yours to fix — it is DNS, in Cloudflare, not code:**

1. Cloudflare → `thoughtpins.com` → DNS → Records.
2. Add `api` → the Railway API service (CNAME to the Railway-provided
   `*.up.railway.app` host), proxy **on**.
3. Add `app` → wherever the web app is served, proxy **on**.
4. In Railway, add both as custom domains on the API service so it issues
   certificates and answers for that Host header.
5. Verify with `python scripts/check_live_endpoints.py` (added in this pass).

Until this is done, **nothing else about the submission matters** — the app is
a login screen with no server.


### F1 — Review account cannot sign in on production (BLOCKER)

`src/thoughtpins/review_seed.py` and `scripts/seed_review_account.py` contain no
invite handling at all — no `invite`, `admitted`, `redeem`, or `is_admin`
reference. Production runs `INVITE_ONLY=true`
(`config.py:239` defaults it true for staging and production).

So the seeded demo account signs in successfully and is then refused by the
invite gate. App Review would see a wall, not the product. This is the exact
shape of a Guideline 2.1 "unable to review" rejection.

Fix in progress.
