import http from "k6/http";
import { check, sleep } from "k6";

const ACCOUNTS = JSON.parse(__ENV.LOAD_ACCOUNTS_JSON || "[]");
if (!ACCOUNTS.length) throw new Error("LOAD_ACCOUNTS_JSON must contain at least one account");

export const options = {
  scenarios: {
    tenant_flow: {
      executor: "per-vu-iterations",
      vus: Number(__ENV.VUS || ACCOUNTS.length),
      iterations: Number(__ENV.ITERATIONS_PER_VU || 2),
      maxDuration: __ENV.MAX_DURATION || "20s",
      gracefulStop: __ENV.GRACEFUL_STOP || "15s",
    },
  },
  thresholds: {
    checks: ["rate>0.99"],
    http_req_failed: ["rate<0.01"],
    http_req_duration: [`p(95)<${Number(__ENV.P95_MS || 1500)}`],
  },
};

const BASE_URL = __ENV.BASE_URL || "http://127.0.0.1:8420";
const REQUEST_TIMEOUT = __ENV.REQUEST_TIMEOUT || "15s";
const PAUSE_SECONDS = Number(__ENV.PAUSE_SECONDS || 2);

export default function () {
  const account = ACCOUNTS[(__VU - 1) % ACCOUNTS.length];
  const headers = {
    Authorization: `Bearer ${account.token}`,
    "Content-Type": "application/json",
    "X-Request-ID": `load-${account.marker}-${__VU}-${__ITER}`,
  };

  const deep = http.get(`${BASE_URL}/v1/health/deep`, {
    headers,
    timeout: REQUEST_TIMEOUT,
    tags: { name: "tenant_health_deep" },
  });
  check(deep, {
    "deep health is healthy": (response) => response.status === 200 && response.json("status") === "ok",
  });

  const ownProbe = http.get(`${BASE_URL}/v1/jobs/${account.probe_job_id}`, {
    headers,
    timeout: REQUEST_TIMEOUT,
    tags: { name: "tenant_own_probe_job" },
  });
  check(ownProbe, { "own probe job visible": (response) => response.status === 200 });

  const foreignProbe = http.get(`${BASE_URL}/v1/jobs/${account.foreign_job_id}`, {
    headers,
    timeout: REQUEST_TIMEOUT,
    tags: { name: "tenant_foreign_probe_job" },
    responseCallback: http.expectedStatuses(404),
  });
  check(foreignProbe, { "foreign probe job hidden": (response) => response.status === 404 });

  const entryText = `I met Load Person ${account.index} at Atlas Cafe and recorded ${account.marker} checkpoint ${__ITER}.`;
  const ingest = http.post(`${BASE_URL}/v1/entries`, JSON.stringify({ text: entryText }), {
    headers,
    timeout: REQUEST_TIMEOUT,
    tags: { name: "tenant_entries_create" },
  });
  check(ingest, {
    "entry queued": (response) => response.status === 202,
  });

  const jobId = ingest.json("job_id");
  if (jobId) {
    const job = http.get(`${BASE_URL}/v1/jobs/${jobId}`, {
      headers,
      timeout: REQUEST_TIMEOUT,
      tags: { name: "tenant_job_status" },
    });
    check(job, { "own job visible": (response) => response.status === 200 });
  }

  const entries = http.get(`${BASE_URL}/v1/entries?page=1&limit=50`, {
    headers,
    timeout: REQUEST_TIMEOUT,
    tags: { name: "tenant_entries_list" },
  });
  const body = entries.body || "";
  check(entries, {
    "own entries visible": (response) => response.status === 200 && body.includes(account.marker),
    "other tenant markers absent": () => ACCOUNTS.every((candidate) => candidate.marker === account.marker || !body.includes(candidate.marker)),
  });

  sleep(PAUSE_SECONDS);
}
