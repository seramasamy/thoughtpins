# Load Scripts

Three [k6](https://k6.io) scenarios. They are not part of the offline release
gate — they need a running API and are run deliberately.

| Script | Exercises |
| --- | --- |
| `k6-health.js` | Readiness under concurrency; the 100-VU run quoted in the README |
| `k6-api-flow.js` | An authenticated write-and-recall path end to end |
| `k6-multi-tenant-flow.js` | Ten tenants at once, checking isolation holds under load rather than only in a unit test |

```bash
k6 run --vus 100 --duration 60s load/k6-health.js
BASE_URL=http://127.0.0.1:8420 API_KEY=... k6 run load/k6-api-flow.js
```

## What a passing run does and does not prove

The recorded results — 100 concurrent health clients with zero failures and a
p95 under 500 ms, ten tenants completing every queued job with no isolation or
dead-letter failure at a 353 ms p95 — come from local Compose against the exact
production topology.

That is evidence about the code. It is not evidence about cloud networking,
managed-database failover, or provider quotas, and the README says so under
[What's unproven](../README.md#whats-unproven). Re-running these against managed
staging is the step that would change that.
