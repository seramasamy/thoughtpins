import http from "k6/http";
import { check } from "k6";

export const options = {
  scenarios: {
    health: {
      executor: "constant-vus",
      vus: Number(__ENV.VUS || 100),
      duration: __ENV.DURATION || "60s",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: [`p(95)<${Number(__ENV.P95_MS || 500)}`],
  },
};

const BASE_URL = __ENV.BASE_URL || "http://localhost:8420";

export default function () {
  const response = http.get(`${BASE_URL}/health`);
  check(response, {
    "health status is 200": (r) => r.status === 200,
    "health says ok": (r) => {
      try {
        return r.json("status") === "ok";
      } catch {
        return false;
      }
    },
  });
}
