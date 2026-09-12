import assert from "node:assert/strict";
import test from "node:test";
import { NativeReviewHolds } from "../scripts/native-review-holds.mjs";

const route = "POST /v1/auth/login";

test("fixture requests remain pending until each explicit release", async () => {
  const holds = new NativeReviewHolds();
  holds.configure([route]);
  let completed = 0;
  const first = holds.wait(route).then(() => { completed++; });
  const second = holds.wait(route).then(() => { completed++; });
  await Promise.resolve();
  assert.equal(completed, 0);
  holds.release(route);
  await first;
  assert.equal(completed, 1);
  holds.release(route);
  await second;
  assert.equal(completed, 2);
});

test("release before arrival permits one request and leaves other routes alone", async () => {
  const holds = new NativeReviewHolds();
  holds.configure([route]);
  holds.release(route);
  await holds.wait(route);
  await holds.wait("GET /v1/client-config");
  let completed = false;
  const next = holds.wait(route).then(() => { completed = true; });
  await Promise.resolve();
  assert.equal(completed, false);
  holds.release(route);
  await next;
});

test("reset releases outstanding work and clears old permissions", async () => {
  const holds = new NativeReviewHolds();
  holds.configure([route, "GET /v1/me"]);
  const pending = [holds.wait(route), holds.wait("GET /v1/me")];
  holds.reset();
  await Promise.all(pending);
  await holds.wait(route);
  holds.configure([route]);
  holds.release(route);
  holds.configure([route]);
  let completed = false;
  const next = holds.wait(route).then(() => { completed = true; });
  await Promise.resolve();
  assert.equal(completed, false);
  holds.reset();
  await next;
});
