import assert from "node:assert/strict";
import test from "node:test";
import {
  GOOGLE_AUTH_ENDPOINT,
  GOOGLE_SIGNIN_MAX_AGE_MS,
  googleAuthorizationUrl,
  readGoogleReturn,
  rememberGoogleSignIn,
  withoutGoogleFragment,
} from "../src/app/googleRedirect.ts";

function memoryStorage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => void values.set(key, value),
    removeItem: (key: string) => void values.delete(key),
    size: () => values.size,
  };
}

const pending = { state: "state-0123456789abcdef", nonce: "nonce-0123456789abcdef", startedAt: 1_000 };

test("the redirect asks Google for an ID token bound to this tab's state and nonce", () => {
  const url = new URL(googleAuthorizationUrl("client.apps.googleusercontent.com", "https://thoughtpins.com/app/", pending));
  assert.equal(`${url.origin}${url.pathname}`, GOOGLE_AUTH_ENDPOINT);
  assert.equal(url.searchParams.get("client_id"), "client.apps.googleusercontent.com");
  assert.equal(url.searchParams.get("redirect_uri"), "https://thoughtpins.com/app/");
  assert.equal(url.searchParams.get("response_type"), "id_token");
  assert.equal(url.searchParams.get("scope"), "openid email profile");
  assert.equal(url.searchParams.get("state"), pending.state);
  assert.equal(url.searchParams.get("nonce"), pending.nonce);
  assert.equal(url.searchParams.get("prompt"), "select_account");
});

test("a matching return yields the token and the nonce the server will check, once", () => {
  const storage = memoryStorage();
  rememberGoogleSignIn(storage, pending);
  const hash = `#state=${pending.state}&id_token=header.payload.signature&authuser=0`;

  assert.deepEqual(readGoogleReturn(hash, storage, 2_000), { kind: "token", idToken: "header.payload.signature", nonce: pending.nonce });
  assert.equal(storage.size(), 0, "the saved state must be spent");
  assert.equal(readGoogleReturn(hash, storage, 2_000).kind, "error", "a replayed fragment must not sign in again");
});

test("a return this tab did not start is refused", () => {
  const storage = memoryStorage();
  rememberGoogleSignIn(storage, pending);
  const result = readGoogleReturn("#state=someone-elses-state&id_token=a.b.c", storage, 2_000);
  assert.deepEqual(result, { kind: "error", message: "Google sign-in could not be verified. Please try again." });

  assert.equal(readGoogleReturn("#state=x&id_token=a.b.c", memoryStorage(), 2_000).kind, "error", "no saved state");
});

test("a stale sign-in is refused", () => {
  const storage = memoryStorage();
  rememberGoogleSignIn(storage, pending);
  const late = pending.startedAt + GOOGLE_SIGNIN_MAX_AGE_MS + 1;
  assert.equal(readGoogleReturn(`#state=${pending.state}&id_token=a.b.c`, storage, late).kind, "error");
});

test("Google's own errors are reported in plain words and spend the state", () => {
  const storage = memoryStorage();
  rememberGoogleSignIn(storage, pending);
  assert.deepEqual(readGoogleReturn(`#state=${pending.state}&error=access_denied`, storage, 2_000), {
    kind: "error",
    message: "Google sign-in was cancelled.",
  });
  assert.equal(storage.size(), 0);
  assert.equal(readGoogleReturn("#error=server_error", memoryStorage(), 2_000).kind, "error");
});

test("an ordinary page load and unreadable storage are handled without throwing", () => {
  assert.deepEqual(readGoogleReturn("", memoryStorage(), 0), { kind: "none" });
  assert.deepEqual(readGoogleReturn("#section", memoryStorage(), 0), { kind: "none" });
  const broken = { getItem: () => { throw new Error("blocked"); }, setItem: () => {}, removeItem: () => {} };
  assert.equal(readGoogleReturn("#state=s&id_token=a.b.c", broken, 0).kind, "error");
  const corrupt = memoryStorage();
  corrupt.setItem("tp-google-signin", "{not json");
  assert.equal(readGoogleReturn("#state=s&id_token=a.b.c", corrupt, 0).kind, "error");
});

test("the ID token is removed from the address, keeping the rest", () => {
  assert.equal(
    withoutGoogleFragment("https://thoughtpins.com/app/?auth=login#state=s&id_token=a.b.c"),
    "https://thoughtpins.com/app/?auth=login",
  );
});
