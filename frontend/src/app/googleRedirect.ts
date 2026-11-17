// Google sign-in by redirect: the standard OpenID Connect flow.
//
// The button used to open Google One Tap. Google and browsers skip One Tap
// whenever the visitor is not already signed in to Google in that browser, has
// dismissed it recently, or blocks third-party cookies, and the button then
// said sign-in "could not open" -- so it failed for most people. A full-page
// redirect to Google's own sign-in page has none of those conditions and loads
// no third-party script. It returns the same ID token, so the server is unchanged.
//
// The page that starts the redirect keeps a single-use state and nonce for the
// tab. The state proves the returning response belongs to this tab; the nonce
// is checked by the server against the one sealed inside the ID token.

export const GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth";
const STORAGE_KEY = "tp-google-signin";
// Long enough to choose an account or sign in to Google, short enough that a
// stale tab cannot finish a sign-in someone else started.
export const GOOGLE_SIGNIN_MAX_AGE_MS = 10 * 60 * 1000;

export type PendingGoogleSignIn = { state: string; nonce: string; startedAt: number };

export type GoogleReturn =
  | { kind: "none" }
  | { kind: "token"; idToken: string; nonce: string }
  | { kind: "error"; message: string };

type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export function googleAuthorizationUrl(clientId: string, redirectUri: string, pending: PendingGoogleSignIn): string {
  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: redirectUri,
    response_type: "id_token",
    scope: "openid email profile",
    nonce: pending.nonce,
    state: pending.state,
    prompt: "select_account",
  });
  return `${GOOGLE_AUTH_ENDPOINT}?${params.toString()}`;
}

export function rememberGoogleSignIn(storage: StorageLike, pending: PendingGoogleSignIn): void {
  storage.setItem(STORAGE_KEY, JSON.stringify(pending));
}

/** Read what Google sent back in the URL fragment. The saved state is spent either way. */
export function readGoogleReturn(hash: string, storage: StorageLike, now: number): GoogleReturn {
  const params = new URLSearchParams(hash.startsWith("#") ? hash.slice(1) : hash);
  const idToken = params.get("id_token");
  const error = params.get("error");
  if (!idToken && !error) return { kind: "none" };
  const pending = takePending(storage);
  if (error) {
    return {
      kind: "error",
      message: error === "access_denied" ? "Google sign-in was cancelled." : "Google sign-in did not complete. Please try again.",
    };
  }
  if (!pending || params.get("state") !== pending.state || now - pending.startedAt > GOOGLE_SIGNIN_MAX_AGE_MS) {
    return { kind: "error", message: "Google sign-in could not be verified. Please try again." };
  }
  return { kind: "token", idToken: idToken as string, nonce: pending.nonce };
}

/** The address without what Google appended: the fragment carries the ID token. */
export function withoutGoogleFragment(href: string): string {
  const url = new URL(href);
  url.hash = "";
  return url.href;
}

function takePending(storage: StorageLike): PendingGoogleSignIn | null {
  let raw: string | null = null;
  try {
    raw = storage.getItem(STORAGE_KEY);
    storage.removeItem(STORAGE_KEY);
  } catch {
    return null;
  }
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<PendingGoogleSignIn>;
    if (typeof value.state === "string" && typeof value.nonce === "string" && typeof value.startedAt === "number") {
      return { state: value.state, nonce: value.nonce, startedAt: value.startedAt };
    }
  } catch {
    // A corrupted entry verifies nothing.
  }
  return null;
}
