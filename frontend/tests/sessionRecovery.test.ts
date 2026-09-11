import assert from "node:assert/strict";
import { test } from "node:test";
import { createSessionRecovery, type SessionTokenPair } from "../src/core/sessionRecovery.ts";

const pair = (name: string): SessionTokenPair => ({ accessToken: name + "-access", refreshToken: name + "-refresh" });
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function fixture(renew: (token: string) => Promise<SessionTokenPair>) {
  let session: SessionTokenPair | null = pair("original");
  const access = { get: () => session, set: (next: SessionTokenPair | null) => { session = next; } };
  const recovery = createSessionRecovery(access, renew, error => [401, 403].includes(Number(error)));
  const original = recovery.capture();
  const recover = () => recovery.recover(original, original?.session.accessToken ?? null);
  return { access, recovery, original, recover };
}

test("concurrent callers consume a refresh token once", async () => {
  let calls = 0;
  const held = deferred<SessionTokenPair>();
  const f = fixture(token => { calls++; assert.equal(token, "original-refresh"); return held.promise; });
  const first = f.recover(), second = f.recover();
  await Promise.resolve();
  assert.equal(calls, 1);
  const next = pair("renewed");
  held.resolve(next);
  assert.deepEqual(await Promise.all([first, second]), [next, next]);
  assert.equal(f.access.get(), next);
});

test("late 401s reuse the rotation without another renewal", async () => {
  let calls = 0;
  const next = pair("renewed");
  const f = fixture(async () => { calls++; return next; });
  assert.equal(await f.recover(), next);
  assert.equal(await f.recover(), next);
  assert.equal(calls, 1);
});

test("a refresh completing after logout cannot restore the account", async () => {
  const held = deferred<SessionTokenPair>();
  const f = fixture(() => held.promise);
  const pending = f.recover();
  f.access.set(null);
  held.resolve(pair("renewed"));
  assert.equal(await pending, null);
  assert.equal(f.access.get(), null);
});

for (const outcome of ["success", "rejection"] as const) {
  test(`an older ${outcome} cannot overwrite a new login or replay its request as that account`, async () => {
    const held = deferred<SessionTokenPair>();
    const f = fixture(() => held.promise);
    const pending = f.recover();
    const other = pair("other-account");
    f.access.set(other);
    if (outcome === "success") {
      held.resolve(pair("renewed"));
      assert.equal(await pending, null);
    } else {
      held.reject(401);
      await assert.rejects(pending, error => error === 401);
    }
    assert.equal(f.access.get(), other);
    assert.equal(await f.recover(), null);
  });
}

for (const status of [0, 429, 503]) {
  test(`renewal failure ${status} preserves the session and can be retried`, async () => {
    let calls = 0;
    const next = pair("renewed");
    const f = fixture(async () => { if (++calls === 1) throw status; return next; });
    await assert.rejects(f.recover(), error => error === status);
    assert.equal(f.access.get(), f.original?.session);
    assert.equal(await f.recover(), next);
    assert.equal(calls, 2);
  });
}

for (const status of [401, 403]) {
  test(`renewal rejection ${status} clears only its own session`, async () => {
    const f = fixture(async () => { throw status; });
    await assert.rejects(f.recover(), error => error === status);
    assert.equal(f.access.get(), null);
  });
}

test("anonymous and mismatched-token requests never renew the current account", async () => {
  let calls = 0;
  const f = fixture(async () => { calls++; return pair("renewed"); });
  assert.equal(await f.recovery.recover(null, null), null);
  assert.equal(await f.recovery.recover(f.original, null), null);
  assert.equal(await f.recovery.recover(f.original, "another-account-access"), null);
  assert.equal(calls, 0);
});
