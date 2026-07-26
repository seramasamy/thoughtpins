// Third-party sign-in helpers. The buttons only render when the deployment
// reports the provider as enabled (client config), and the flow only runs when
// a public client ID is provided at build time. When a provider is shown but a
// client ID is not configured, the caller surfaces a clear message rather than
// failing silently — these are real integrations awaiting configuration, not
// mock controls.

export type OAuthProvider = "google" | "apple";

export class OAuthNotConfiguredError extends Error {
  constructor(provider: OAuthProvider) {
    super(`${provider === "google" ? "Google" : "Apple"} sign-in is not configured for this deployment yet.`);
    this.name = "OAuthNotConfiguredError";
  }
}

const GOOGLE_CLIENT_ID = (import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined) || "";
const APPLE_CLIENT_ID = (import.meta.env.VITE_APPLE_CLIENT_ID as string | undefined) || "";

export function oauthClientConfigured(provider: OAuthProvider): boolean {
  return provider === "google" ? Boolean(GOOGLE_CLIENT_ID) : Boolean(APPLE_CLIENT_ID);
}

function loadScript(src: string, id: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if (document.getElementById(id)) return resolve();
    const script = document.createElement("script");
    script.src = src;
    script.id = id;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Could not reach the sign-in provider. Check your connection and try again."));
    document.head.appendChild(script);
  });
}

export type OAuthResult = {
  idToken: string;
  authorizationCode?: string;
  redirectUri?: string;
  nonce?: string;
  displayName?: string;
};

async function signInWithGoogle(): Promise<OAuthResult> {
  if (!GOOGLE_CLIENT_ID) throw new OAuthNotConfiguredError("google");
  await loadScript("https://accounts.google.com/gsi/client", "tp-gsi");
  const google = (window as unknown as { google?: any }).google;
  if (!google?.accounts?.id) throw new Error("Google sign-in is temporarily unavailable.");
  const nonce = randomOAuthValue();
  return await new Promise<OAuthResult>((resolve, reject) => {
    google.accounts.id.initialize({
      client_id: GOOGLE_CLIENT_ID,
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
  if (!APPLE_CLIENT_ID) throw new OAuthNotConfiguredError("apple");
  await loadScript("https://appleid.cdn-apple.com/appleauth/static/jsapi/appleid/1/en_US/appleid.auth.js", "tp-appleid");
  const AppleID = (window as unknown as { AppleID?: any }).AppleID;
  if (!AppleID?.auth) throw new Error("Apple sign-in is temporarily unavailable.");
  const redirectUri = window.location.origin + import.meta.env.BASE_URL;
  const state = randomOAuthValue();
  const nonce = randomOAuthValue();
  AppleID.auth.init({
    clientId: APPLE_CLIENT_ID,
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
