# Pricing plan (not implemented)

Notes for a future release. **Nothing here is wired up.** No billing code,
no plan field, no checkout, no store purchase surface exists, and
`scripts/check_free_launch.py` fails the build if any of that appears.

The only part live today is the free-tier spend cap, which is configuration on
an existing metering system (`src/thoughtpins/usage.py`), not commerce.

## Shape

Cost recovery, not margin. Each tier's price matches the provider spend it
allows, so a paying user funds their own usage and nothing more.

| Tier | Price | Monthly AI spend allowance | State |
|---|---|---|---|
| **Free** | $0 | $5.00 | Live (cap enforced by config) |
| **Sustain** | $5 / month | $5.00 | Not built |
| **Sustain Plus** | $10 / month | $10.00 | Not built |

Naming rationale: the paid tiers buy continued use, not extra features, so the
names should not imply a better product. "Pro" or "Premium" would promise
capability that does not exist — every tier is the same app. "Sustain" says
what the money actually does.

A user reaching $5 of measured spend has used roughly a few hundred chat turns
plus journal enrichment. Most people will never approach it.

## What already exists

- Per-user monthly spend, metered from real provider token counts
  (`llm_usage_events`), priced from a configurable per-model map.
- `USAGE_MONTHLY_BUDGET_USD`, currently `5.00`.
- `USAGE_ENFORCEMENT_ENABLED`, currently **off**: spend is recorded and
  reported but nothing is blocked yet.
- Graceful degradation already written: at the cap, chat falls back to
  answering from the user's own memories without a model call, and ingestion
  returns HTTP 402. Queued work parks as retryable rather than failing, so it
  resumes when the month resets.
- `USAGE_GLOBAL_MONTHLY_BUDGET_USD`, a platform-wide ceiling independent of
  per-user caps.

So the metering half of billing is done. What is missing is commerce.

## What building this would require

1. A `plan` column on the user row, with the per-user budget read from the plan
   rather than one global config value.
2. Stripe subscriptions: checkout, customer portal, and webhook handling for
   created, renewed, failed, and cancelled events. Webhooks are the part that
   has to be right — a missed cancellation silently grants free service, and a
   missed renewal locks out a paying user.
3. An upgrade path in the app at the moment the cap is reached, since that is
   the only point a user has a reason to care.
4. Proration and downgrade behaviour, including what happens to spend already
   recorded in the current month.

## Store constraints

`deploy/store/commerce-policy.json` marks the first release free, with
`future_monetization_requires_new_review: true`. Turning on payments means a new
App Store review.

More restrictive: Apple requires digital subscriptions consumed inside an iOS
app to use in-app purchase, which takes a 15–30% commission. A $5 tier priced to
match provider cost would then lose money on iOS. Options are to sell only on
the web and keep the iOS app free, or to raise the iOS price to absorb the
commission. Worth deciding before building any of it.

## Suggested sequencing

Run free with enforcement on and watch real spend for a while first. The right
cap is an observation, not a guess, and if typical use lands far below $5 the
paid tiers may not be needed at all.

## Private launch (invite only)

`INVITE_ONLY` defaults on in staging and production. Registration stays open —
accounts are created and their details kept — but nothing that reads or writes
memory works until a code is redeemed. Data rights are never gated: a waiting
account can still read, export, change sign-in details, and delete itself.

Issue codes with `scripts/create_invite_code.py`. Against production, point
`DATABASE_URL` at Railway's `DATABASE_PUBLIC_URL` (the internal hostname does not
resolve from a laptop):

```
python scripts/create_invite_code.py --label "friends" --uses 1 --count 5
python scripts/create_invite_code.py --list
python scripts/create_invite_code.py --revoke <id>
```

Only the hash is stored, so a code cannot be shown again after minting. Ending
the private launch is one variable: set `INVITE_ONLY=false` and everyone who
already registered is admitted, with no migration and no data change.
