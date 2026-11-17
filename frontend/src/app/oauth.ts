// Third-party sign-in helpers. The buttons only render when the deployment
// reports the provider as enabled (client config), and the flow only runs when
// a public client ID is available. When a provider is shown but a client ID is
// not configured, the caller surfaces a clear message rather than failing
// silently — these are real integrations awaiting configuration, not mock
// controls.
//
// The client ID is taken from the server's client config first, falling back to
// the build-time variable. OAuth client IDs are public by design, and reading
// one at runtime means rotating it does not require rebuilding the bundle — a
// build-only value silently yields an enabled-looking button that cannot work.

import {
  googleAuthorizationUrl,
  readGoogleReturn,
  rememberGoogleSignIn,
  withoutGoogleFragment,
  type GoogleReturn,
} from "./googleRedirect";
import { loadProviderScript as loadScript } from "./providerScript";

export type OAuthProvider = "google" | "apple";

export class OAuthNotConfiguredError extends Error {
  constructor(provider: OAuthProvider) {
    super(`${provider === "google" ? "Google" : "Apple"} sign-in is not configured for this deployment yet.`);
    this.name = "OAuthNotConfiguredError";
  }
}

const BUILD_GOOGLE_CLIENT_ID = (import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined) || "";
const BUILD_APPLE_CLIENT_ID = (import.meta.env.VITE_APPLE_CLIENT_ID as string | undefined) || "";

const runtimeClientIds: { google: string; apple: string } = { google: "", apple: "" };

/** Supply client IDs from the server's client config once it has loaded. */
export function setOAuthClientIds(ids: { google?: string | null; apple?: string | null }): void {
  runtimeClientIds.google = (ids.google || "").trim();
  runtimeClientIds.apple = (ids.apple || "").trim();
}

function clientIdFor(provider: OAuthProvider): string {
  return provider === "google"
    ? runtimeClientIds.google || BUILD_GOOGLE_CLIENT_ID
    : runtimeClientIds.apple || BUILD_APPLE_CLIENT_ID;
}

export function oauthClientConfigured(provider: OAuthProvider): boolean {
  return Boolean(clientIdFor(provider));
}

const APPLE_SCRIPT = "https://appleid.cdn-apple.com/appleauth/static/jsapi/appleid/1/en_US/appleid.auth.js";

export function prepareAppleSignIn(): void {
  if (oauthClientConfigured("apple")) void loadScript(APPLE_SCRIPT, "tp-appleid").catch(() => {});
}

export type OAuthResult = {
  idToken: string;
  authorizationCode?: string;
  redirectUri?: string;
  nonce?: string;
  displayName?: string;
};

/** Leave for Google's sign-in page; Google sends the tab back to the app's own address. */
function startGoogleSignIn(): Promise<OAuthResult> {
  const clientId = clientIdFor("google");
  if (!clientId) return Promise.reject(new OAuthNotConfiguredError("google"));
  const pending = { state: randomOAuthValue(), nonce: randomOAuthValue(), startedAt: Date.now() };
  try {
    rememberGoogleSignIn(sessionStore(), pending);
  } catch {
    return Promise.reject(new Error("Google sign-in needs this site's storage. Allow it, or use email or phone instead."));
  }
  window.location.assign(googleAuthorizationUrl(clientId, appRedirectUri(), pending));
  // The page is leaving for Google; the form stays busy until it has gone.
  return new Promise<OAuthResult>(() => {});
}

let googleReturn: GoogleReturn | undefined;

/** What Google sent back to this page load: read once, then removed from the address bar. */
export function takeGoogleReturn(): GoogleReturn {
  if (googleReturn) return googleReturn;
  googleReturn = readGoogleReturn(window.location.hash, sessionStore(), Date.now());
  if (googleReturn.kind !== "none") {
    window.history.replaceState(window.history.state, "", withoutGoogleFragment(window.location.href));
  }
  return googleReturn;
}

type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;

const unavailableStorage: StorageLike = {
  getItem: () => null,
  setItem: () => {
    throw new Error("Session storage is unavailable");
  },
  removeItem: () => {},
};

function sessionStore(): StorageLike {
  try {
    return window.sessionStorage;
  } catch {
    return unavailableStorage;
  }
}

function appRedirectUri(): string {
  return window.location.origin + import.meta.env.BASE_URL;
}

async function signInWithApple(): Promise<OAuthResult> {
  const clientId = clientIdFor("apple");
  if (!clientId) throw new OAuthNotConfiguredError("apple");
  await loadScript(APPLE_SCRIPT, "tp-appleid");
  const AppleID = (window as unknown as { AppleID?: any }).AppleID;
  if (!AppleID?.auth) throw new Error("Apple sign-in is temporarily unavailable.");
  const redirectUri = appRedirectUri();
  const state = randomOAuthValue();
  const nonce = randomOAuthValue();
  AppleID.auth.init({
    clientId,
    scope: "name email",
    redirectURI: redirectUri,
    state,
    nonce,
    usePopup: true,
  });
  const data = await AppleID.auth.signIn();
  const idToken: string | undefined = data?.authorization?.id_token;
  const authorizationCode: string | undefined = data?.authorization?.code;
  const returnedState: string | undefined = data?.authorization?.state;
  if (!idToken || !authorizationCode) throw new Error("Apple sign-in did not return a complete credential.");
  if (!returnedState || returnedState !== state) throw new Error("Apple sign-in state validation failed.");
  const name = data?.user?.name;
  const displayName = name ? [name.firstName, name.lastName].filter(Boolean).join(" ") : undefined;
  return { idToken, authorizationCode, redirectUri, nonce, displayName };
}

export function signInWithProvider(provider: OAuthProvider): Promise<OAuthResult> {
  return provider === "google" ? startGoogleSignIn() : signInWithApple();
}

function randomOAuthValue(): string {
  if (!globalThis.crypto?.getRandomValues) {
    throw new Error("Secure sign-in is unavailable in this browser context.");
  }
  const bytes = new Uint8Array(32);
  globalThis.crypto.getRandomValues(bytes);
  const binary = Array.from(bytes, (value) => String.fromCharCode(value)).join("");
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/u, "");
}
