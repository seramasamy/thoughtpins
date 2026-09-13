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

async function signInWithGoogle(): Promise<OAuthResult> {
  const clientId = clientIdFor("google");
  if (!clientId) throw new OAuthNotConfiguredError("google");
  await loadScript("https://accounts.google.com/gsi/client", "tp-gsi");
  const google = (window as unknown as { google?: any }).google;
  if (!google?.accounts?.id) throw new Error("Google sign-in is temporarily unavailable.");
  const nonce = randomOAuthValue();
  return await new Promise<OAuthResult>((resolve, reject) => {
    google.accounts.id.initialize({
      client_id: clientId,
      nonce,
      callback: (response: { credential?: string }) => {
        if (response?.credential) resolve({ idToken: response.credential, nonce });
        else reject(new Error("Google sign-in was cancelled."));
      },
    });
    google.accounts.id.prompt((notification: any) => {
      if (notification?.isNotDisplayed?.() || notification?.isSkippedMoment?.()) {
        reject(new Error("Google sign-in could not open. Please try email or phone instead."));
      }
    });
  });
}

async function signInWithApple(): Promise<OAuthResult> {
  const clientId = clientIdFor("apple");
  if (!clientId) throw new OAuthNotConfiguredError("apple");
  await loadScript(APPLE_SCRIPT, "tp-appleid");
  const AppleID = (window as unknown as { AppleID?: any }).AppleID;
  if (!AppleID?.auth) throw new Error("Apple sign-in is temporarily unavailable.");
  const redirectUri = window.location.origin + import.meta.env.BASE_URL;
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
  return provider === "google" ? signInWithGoogle() : signInWithApple();
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
