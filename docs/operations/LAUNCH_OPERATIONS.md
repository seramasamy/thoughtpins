# Launch operations — rollback, monitoring, backups, crash reports

What to do when production is wrong, and what is watching it in the meantime.
Written 2026-08-26. Where something does not exist, it says so and gives the
cost of the smallest version rather than the ideal one.

**Read the honesty note first.** Three things in here could not be rehearsed
from the machine this was written on: it has no Railway CLI, no `psql`, no
`pg_dump` and no Docker. Anything marked **UNREHEARSED** is written from the
code and the provider's documented behaviour, and the first person to run it
should confirm each step and correct this file.

---

## 1. Rollback — the 11pm procedure

**UNREHEARSED.** The runbook's previous rollback section was provider-neutral
prose with no commands: "Start the previous known-good image", without saying
how. That is the one step someone follows under pressure, so it is the one that
must not be prose.

### Rolling back the code

Railway keeps every previous deployment and can redeploy one directly.

**Dashboard, which is the path to use at 11pm:**

1. railway.app → the project → the **api** service.
2. **Deployments** tab. The list is newest first.
3. Find the last deployment that was healthy. Its commit SHA is shown.
4. **⋮** on that row → **Redeploy**.
5. Watch until it reports Active. Expect one to three minutes.
6. Repeat for the **worker** service. **Do not skip this** — the API and the
   worker are separate services, and rolling back one without the other leaves
   a worker running code the API no longer speaks to.

**Verify, in this order:**

```bash
curl -s https://api.thoughtpins.com/ready            # must be 200, not 503
curl -s https://api.thoughtpins.com/v1/client-config | grep api_version
python scripts/smoke_registration.py --base-url https://api.thoughtpins.com
```

The last one is the real check: it registers a throwaway account, proves it is
admitted, and deletes it. A rollback that leaves registration broken is not a
successful rollback.

### The part that is not just code

**A rollback across a migration is not a redeploy.** Every one of the 26
Alembic revisions defines a real `downgrade()` — none is a stub — but the
PostgreSQL-only branches inside them (`DROP POLICY`, `DISABLE ROW LEVEL
SECURITY`, `GRANT`) have **never been executed**: CI runs downgrades against
SQLite, where `_is_postgres()` is false and every one of those branches is
skipped.

So: if the bad deploy included a migration, a code-only rollback may leave the
schema ahead of the code. Prefer rolling **forward** with a fix. If you must
downgrade, do it against a restored copy first (section 3) and expect the
PostgreSQL branches to be running for the first time.

### Turning the app off without a rollback

Faster than a rollback and reversible in one variable:

| Situation | Variable | Effect |
|---|---|---|
| Something is broken but data is safe | `MAINTENANCE_MODE=true` | Banner in the app, 503 with `Retry-After` on writes, reads still allowed |
| A shipped build is dangerous | `MIN_IOS_VERSION=<above the bad build>` | Every copy shows "Update Thought Pins to continue" with an App Store link |

Both take a **restart** — configuration is read once at import, so a Railway
variable change redeploys the service. Budget one to three minutes, and note
`healthcheckTimeout` is 300s.

Both were fired against the shipping binary on 2026-08-26 and behave correctly:
the update screen shows both version numbers and a working store button; the
maintenance banner leaves the whole app usable underneath.

**Before using `MIN_IOS_VERSION` in anger:** `store_urls.ios` is `null` on
production today, so the update screen falls back to "Search for Thought Pins in
the App Store". Set `IOS_STORE_URL` once the App Store listing exists.

---

## 2. Monitoring — what watches production

**Today: nothing alerts a human.** Every monitoring artifact is either a probe
an orchestrator polls, an endpoint nothing polls, or a manual runbook step.
There is no uptime vendor, no Prometheus, no PagerDuty. Sentry is supported and
off.

### Fixed in this pass

- **The container health check pointed at `/health`**, which returns `"ok"` with
  the database down, Redis down and no worker alive. Railway and Fly would have
  kept a dead container in rotation, green. Both now point at `/ready`, which
  actually checks dependencies and 503s.
- **The worker never initialised Sentry.** It never called `setup_logging()`, so
  the one process whose failures nobody sees was the only one not reporting
  them. It does now — set `SENTRY_DSN` and both processes report.
- **`/v1/metrics` carried no queue or worker signal.** Depth and heartbeat age
  were computed and unreachable. Three gauges are now exposed:
  `thoughtpins_worker_heartbeat_age_seconds`, `thoughtpins_queue_depth`,
  `thoughtpins_worker_up`. Unknown reads as `-1`, except `up`, which reads `0` —
  a monitor that cannot reach the worker should alert, not shrug.

### The smallest useful setup, and what it costs

**Do this before launch. Budget: £0 and about twenty minutes.**

1. **An uptime check on a real endpoint.** Any of UptimeRobot, Better Stack or
   Cronitor has a free tier that covers this.
   - URL: `https://api.thoughtpins.com/ready`
   - Interval: 5 minutes (free tiers allow this)
   - Alert to: your email **and** your phone
   - **Not `/health`** — that endpoint cannot fail.

2. **Sentry for errors.** Free tier is 5,000 events a month, which is far more
   than this will produce. Create a project, set `SENTRY_DSN` on **both** the
   api and worker services. Nothing else is needed; the code is already there.

3. **A worker-stall alert.** The failure that costs most and shows least: the
   API stays green, requests succeed, and entries never finish processing.
   Point a monitor at `/v1/metrics` and alert when
   `thoughtpins_worker_up` is `0` for more than ten minutes.
   `/v1/metrics` is authenticated, so this needs a long-lived token — if that is
   awkward, alert on `/ready` returning 503 instead, which covers the same
   failure more bluntly.

That is the whole recommendation. Anything more — dashboards, tracing,
percentile SLOs — is not worth it for one person and a first release.

---

## 3. Backups and restore

**UNREHEARSED against PostgreSQL.** What follows is measured where it says
measured and inferred where it says inferred.

### What exists

- A daemon thread inside the API makes a local ZIP of `data/`, `vault/`,
  `reports/` and a local Qdrant directory. It is **not** a database backup, and
  it is scheduled by a Python sleep loop rather than by cron.
- `scripts/restore_backup.py` and `scripts/smoke_restore_backup.py` restore and
  verify those archives. **Rehearsed 2026-08-26: 554 files, 702 KB, restored and
  verified in 1.4 seconds.** That path works.
- A `pg_dump`/`pg_restore` drill script exists but restores only into a scratch
  database on a local Compose stack.

### What does not exist

**There is no scheduled backup of the production database, in this repository.**
Railway's managed Postgres offers backups, but nothing in the repo configures,
verifies or even mentions them. Whether production data is recoverable today
depends on a dashboard setting nobody has written down.

### Do this before launch

1. **Check the Railway dashboard now.** Project → the Postgres service →
   Backups. Record in this file: the plan, whether backups are on, the retention
   window, and the date you checked. Five lines.
2. **If they are off, turn them on.** This is the single highest-value
   operational action available and it is a toggle.
3. **Rehearse one restore.** Restore the newest backup into a scratch database,
   point a local API at it, and confirm the review account's entries are there.
   Record the wall-clock time here. An untested backup is not a backup.

---

## 4. Crash visibility on iOS

**There is no crash SDK, and that is a deliberate trade.** No Sentry,
Crashlytics, Bugsnag, MetricKit or uncaught-exception handler. After GoogleSignIn
was removed this session, the iOS app has **zero third-party dependencies of any
kind**, which is a defensible position for a privacy-positioned app and one that
is easy to explain to a reviewer.

### What you get free, with no SDK

**Xcode Organizer crash reports.** Apple collects crashes from TestFlight and
App Store users who have opted into sharing diagnostics, symbolicates them, and
groups them. They appear in Xcode → Window → Organizer → Crashes, and in App
Store Connect. There is no code to write.

Two caveats worth knowing before relying on it:

- It needs **Xcode**, on a Mac, to read comfortably. From a PC, App Store
  Connect shows crash counts but the good symbolicated view is Organizer.
- It only covers users who share diagnostics, and it is not real time — expect
  hours to a day.

**Are the dSYMs the right ones?** Yes. Release builds use `dwarf-with-dsym`;
`ExportOptions.plist` sets `uploadSymbols: true`, so the symbols go to Apple
with the build; and GitHub Actions keeps the archive *and* its dSYMs as a 30-day
artifact, so a crash report from a build in that window can be symbolicated by
hand if Apple's copy is ever missing. Xcode Cloud's TestFlight distribution
uploads symbols the same way.

### Recommendation

**Ship v1 with no crash SDK.** Use Xcode Organizer. Revisit only if you see
crashes you cannot reproduce and cannot diagnose from Organizer — at which point
the honest options are MetricKit (Apple's own, no third party, but coarse) or
Sentry's Apple SDK (better, but it is a third-party SDK in a privacy app and
changes what you must declare on the App Privacy questionnaire).

Do not add one now. It would have to be disclosed, it is the kind of thing a
reviewer asks about, and Organizer is genuinely adequate at this scale.

**One thing that is already there:** `POST /v1/safety/reports` takes a free-form
`metadata` object and a `general` target type, so a "something went wrong" report
carrying build number and OS version needs no schema change — only a screen. Not
built; noted because it is cheaper than an SDK if it ever becomes necessary.
