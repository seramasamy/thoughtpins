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

### Provider naming: already generic, and already enforced.

Requested: ensure a particular provider's name appears nowhere and that the
configuration reads as a generic key.

Verified — that vendor name appears in **zero files**, and this is not luck:
it is on the forbidden-term list in `scripts/forbidden_scan.py`, which runs in
the release gate and in CI. The build fails if the word is committed anywhere.
(This document tripped that scan on its first draft, which is how I confirmed
the rule is live rather than aspirational.)

The client in `src/thoughtpins/llm/` is written against any OpenAI-compatible
endpoint, and the environment contract is already provider-neutral:

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
| 1 | Review account blocked by invite gate | **done** — real invite minted + redeemed, 2 tests |
| 2 | Invite gate toggle | **done** — already `INVITE_ONLY`; stays true in prod, website gated |
| 3 | Demo account + credentials handoff | **done** — seeder + CLI reports admission |
| 4 | Apple review notes | **done** — `REVIEW_NOTES.md`, paste-ready |
| 5 | `apple-submission/` package | **done** |
| 6 | Post-developer-account runbook | **done** — `AFTER_DEVELOPER_ACCOUNT.md`, 20 steps |
| 7 | Review-trigger sweep | **done** — no paywall bypass, no IDFA/ATT/private API |
| 8 | Registration + support email + legal | **done in code**; you must verify the two mailboxes |
| 9 | Emulator run | **done** — Android booted, app installed, launched, screenshotted |
| 10 | GitHub presentation + architecture graphics | **done** — `docs/architecture/RETRIEVAL_ARCHITECTURE.md` |
| 11 | Technical debt verified fixed | in progress |
| 12 | DNS | `api.` registered in Railway; **one Cloudflare CNAME left for you** — see F0. `app.` retired. |

## What is left, and who does it

**You:**
1. Create the one `api` CNAME + TXT in Cloudflare (**F0**) — unblocks both apps
2. Verify `support@thoughtpins.com` and `invite@thoughtpins.com` receive mail
3. Set `APPLE_OAUTH_CLIENT_IDS` in Railway once the developer account exists.
   Production currently reports `oauth_google_enabled: true` and
   `oauth_apple_enabled: false`, and Guideline 4.8 requires Sign in with Apple
   wherever a third-party sign-in is offered. This is a rejection if shipped.
4. Get a Mac (or rent one) — nothing Swift can be compiled without it
5. Apple Developer enrollment → `AFTER_DEVELOPER_ACCOUNT.md` Stage 1

**Then, on the Mac:** `swift test`, first Xcode build, simulator matrix,
screenshots. Expect first-build compile errors — ~400 lines of SwiftUI have
never been through a compiler.

---

## Findings log

### F0 — `api.thoughtpins.com` had no DNS record (RESOLVED IN RAILWAY, ONE STEP LEFT FOR YOU)

The hostname compiled into both mobile builds returned NXDOMAIN, so the app had
no backend at all. The Android emulator showed exactly that on first launch:
"Could not reach Thought Pins". It would have been a Guideline 2.1 rejection
with the app never actually reviewed.

**The backend was never the problem.** Verified directly:

| Endpoint | Result |
|---|---|
| `api-production-537b.up.railway.app/v1/client-config` | **200** |
| `api-production-537b.up.railway.app/health` | **200** |
| `thoughtpins.com/v1/client-config` | **200** |
| `thoughtpins.com/app` | **200** |

The API service is healthy, and `thoughtpins.com` is already a Railway custom
domain on it — which is why the marketing site, the web app and the API all
answer there today. Only the `api.` alias was missing.

`api.thoughtpins.com` is now registered as a custom domain on the `api` service
(port 8420). It is inert until DNS points at it.

**The one step left is yours, in Cloudflare → `thoughtpins.com` → DNS → Records:**

| Type | Name | Value | Proxy |
|---|---|---|---|
| CNAME | `api` | `rl0w7xx5.up.railway.app` | **DNS only** (grey cloud) |
| TXT | `_railway-verify.api` | `railway-verify=537ef6db8bf1139c2f0ace88a746d9dbd34aa290a6610f2b938d168243b6ec7f` | n/a |

Railway issues the certificate itself, so the CNAME must be **unproxied** or the
ownership check cannot complete. Then:

```bash
python scripts/check_live_endpoints.py      # expect 7/7
railway domain status d95f60a7-499f-4c26-8716-202a7bd43bd7
```

**`app.thoughtpins.com` was retired rather than created.** Railway's Hobby plan
allows two custom domains per service and the `api` service now uses both
(apex + `api.`). The subdomain was a pure alias of `thoughtpins.com/app`, which
already returns 200, so 23 files were updated to point at the path instead of
paying for a hostname that adds nothing. `WEB_APP_URL` is now
`https://thoughtpins.com/app` and `CORS_ALLOW_ORIGINS` is `https://thoughtpins.com`.

**Why the gate did not catch any of this:** `scripts/check_domain_readiness.py`
compares strings in config files. It never resolves a name or makes a request,
so it passed while the hostname did not exist. `scripts/check_live_endpoints.py`
now asks the real question, and is deliberately outside the offline gate because
it needs the network.

**A note on how the Railway domain got added.** `railway domain` with no
arguments is not a read command — it creates a service domain. Running it to
inspect state created a public domain on the **worker** service, which is a
Celery process that should never be publicly exposed. It was deleted
immediately (`railway domain delete`), and `railway domain list --service worker`
now reports none. Use explicit subcommands.


### F1 — Review account cannot sign in on production (BLOCKER)

`src/thoughtpins/review_seed.py` and `scripts/seed_review_account.py` contain no
invite handling at all — no `invite`, `admitted`, `redeem`, or `is_admin`
reference. Production runs `INVITE_ONLY=true`
(`config.py:239` defaults it true for staging and production).

So the seeded demo account signs in successfully and is then refused by the
invite gate. App Review would see a wall, not the product. This is the exact
shape of a Guideline 2.1 "unable to review" rejection.

Fix in progress.
