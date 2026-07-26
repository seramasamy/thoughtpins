import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  scenarios: {
    app_flow: {
      executor: "constant-vus",
      vus: Number(__ENV.VUS || 10),
      duration: __ENV.DURATION || "60s",
      gracefulStop: __ENV.GRACEFUL_STOP || "10s",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.02"],
    http_req_duration: [`p(95)<${Number(__ENV.P95_MS || 1000)}`],
  },
};

const BASE_URL = __ENV.BASE_URL || "http://localhost:8420";
const PASSWORD = __ENV.PASSWORD || "correct horse battery staple";
const ENTRY_TEXT = __ENV.ENTRY_TEXT || "k6 app-flow entry: checked auth, async entry queue, jobs, and list APIs.";
const REQUEST_TIMEOUT = __ENV.REQUEST_TIMEOUT || "10s";

export function setup() {
  if (__ENV.ACCESS_TOKEN) {
    return { token: __ENV.ACCESS_TOKEN };
  }

  const email = __ENV.EMAIL || `k6-${Date.now()}-${Math.random().toString(16).slice(2)}@example.com`;
  if ((__ENV.REGISTER || "true").toLowerCase() === "true") {
    const register = http.post(
      `${BASE_URL}/v1/auth/register`,
      JSON.stringify({ email, password: PASSWORD }),
      { headers: { "Content-Type": "application/json" }, timeout: REQUEST_TIMEOUT, tags: { name: "auth_register" } },
    );
    check(register, {
      "register accepted or already exists": (r) => [200, 403, 409].includes(r.status),
    });
  }

  const login = http.post(
    `${BASE_URL}/v1/auth/login`,
    JSON.stringify({ email, password: PASSWORD }),
    { headers: { "Content-Type": "application/json" }, timeout: REQUEST_TIMEOUT, tags: { name: "auth_login" } },
  );
  check(login, { "login ok": (r) => r.status === 200 });
  return { token: login.json("access_token") };
}

export default function (data) {
  const headers = {
    Authorization: `Bearer ${data.token}`,
    "Content-Type": "application/json",
    "X-Request-ID": `k6-${__VU}-${__ITER}`,
  };

  const deep = http.get(`${BASE_URL}/v1/health/deep`, {
    headers,
    timeout: REQUEST_TIMEOUT,
    tags: { name: "health_deep" },
  });
  check(deep, {
    "deep health reachable": (r) => r.status === 200,
    "deep health not failed": (r) => ["ok", "degraded"].includes(r.json("status")),
  });

  const ingest = http.post(
    `${BASE_URL}/v1/entries`,
    JSON.stringify({ text: `${ENTRY_TEXT} vu=${__VU} iter=${__ITER}` }),
    { headers, timeout: REQUEST_TIMEOUT, tags: { name: "entries_create" } },
  );
  check(ingest, {
    "entry accepted": (r) => [200, 202].includes(r.status),
  });

  const jobId = ingest.json("job_id");
  if (jobId) {
    const job = http.get(`${BASE_URL}/v1/jobs/${jobId}`, {
      headers,
      timeout: REQUEST_TIMEOUT,
      tags: { name: "jobs_status" },
    });
    check(job, { "job visible": (r) => r.status === 200 });
  }

  const jobs = http.get(`${BASE_URL}/v1/jobs?page=1&limit=10`, {
    headers,
    timeout: REQUEST_TIMEOUT,
    tags: { name: "jobs_list" },
  });
  check(jobs, { "jobs list ok": (r) => r.status === 200 });

  const entries = http.get(`${BASE_URL}/v1/entries?page=1&limit=10`, {
    headers,
    timeout: REQUEST_TIMEOUT,
    tags: { name: "entries_list" },
  });
  check(entries, { "entries list ok": (r) => r.status === 200 });

  sleep(1);
}
