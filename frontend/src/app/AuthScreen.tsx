import { ArrowLeft, Loader2, Mail, Moon, ShieldCheck, Sun } from "lucide-react";
import type { FormEvent } from "react";
import { useEffect, useState } from "react";
import { api, type ApiSession } from "../api";
import type { Notice } from "./types";
import { messageFromError } from "./types";
import type { ClientConfigResponse } from "../types";
import { BrandMark, IconButton, NoticeBanner, PrimaryButton } from "../components/ui";
import { setOAuthClientIds, signInWithProvider, type OAuthProvider } from "./oauth";
import { toggleTheme, useResolvedTheme } from "../core/theme";

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
      <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62Z" />
      <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.81.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.34A9 9 0 0 0 9 18Z" />
      <path fill="#FBBC05" d="M3.97 10.72a5.4 5.4 0 0 1 0-3.44V4.94H.96a9 9 0 0 0 0 8.12l3.01-2.34Z" />
      <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.46 3.44 1.35l2.58-2.58C13.47.9 11.43 0 9 0A9 9 0 0 0 .96 4.94l3.01 2.34C4.68 5.16 6.66 3.58 9 3.58Z" />
    </svg>
  );
}

function AppleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M17.05 12.54c-.02-2.05 1.68-3.03 1.75-3.08-.95-1.4-2.44-1.59-2.97-1.61-1.26-.13-2.47.74-3.11.74-.64 0-1.63-.72-2.68-.7-1.38.02-2.65.8-3.36 2.03-1.43 2.49-.37 6.17 1.03 8.19.68.99 1.5 2.1 2.56 2.06 1.03-.04 1.42-.66 2.66-.66 1.24 0 1.59.66 2.68.64 1.11-.02 1.81-1.01 2.49-2 .78-1.15 1.11-2.26 1.12-2.32-.02-.01-2.15-.83-2.17-3.27ZM15.02 6.5c.56-.68.94-1.63.84-2.58-.81.03-1.79.54-2.37 1.22-.52.6-.98 1.56-.86 2.48.9.07 1.83-.46 2.39-1.12Z" />
    </svg>
  );
}

export function AuthScreen({
  clientConfig,
  setSession,
  notice,
  setNotice,
}: {
  clientConfig: ClientConfigResponse | null;
  setSession: (session: ApiSession | null) => void;
  notice: Notice | null;
  setNotice: (notice: Notice | null) => void;
}) {
  const [mode, setMode] = useState<"login" | "register">(() => requestedAuthMode());
  const [identifier, setIdentifier] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [legalAccepted, setLegalAccepted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [oauthBusy, setOauthBusy] = useState<OAuthProvider | null>(null);
  const [magicBusy, setMagicBusy] = useState(false);
  const [magicSentTo, setMagicSentTo] = useState<string | null>(null);
  const [magicCode, setMagicCode] = useState("");
  // Starts true when the URL carries a token so the form never flashes before
  // the automatic sign-in resolves.
  const [consumingMagicLink, setConsumingMagicLink] = useState(() => magicTokenFromUrl() !== null);
  const theme = useResolvedTheme();
  const registrationLocked = clientConfig?.registration_locked ?? true;
  const showGoogle = clientConfig?.oauth_google_enabled ?? false;
  const showApple = clientConfig?.oauth_apple_enabled ?? false;
  const showOAuth = showGoogle || showApple;
  const magicLinkEnabled = clientConfig?.magic_link_enabled ?? false;
  const maintenanceMessage = clientConfig?.maintenance_mode
    ? clientConfig.maintenance_message || "Thought Pins is in maintenance for a short upgrade. Please try again soon."
    : null;

  useEffect(() => {
    if (registrationLocked && mode === "register") {
      selectMode("login");
    }
  }, [mode, registrationLocked]);

  // Hand the server-provided client IDs to the OAuth helpers before any button
  // can be pressed.
  useEffect(() => {
    setOAuthClientIds({
      google: clientConfig?.oauth_google_client_id,
      apple: clientConfig?.oauth_apple_client_id,
    });
  }, [clientConfig?.oauth_google_client_id, clientConfig?.oauth_apple_client_id]);

  // Complete a sign-in arriving from an emailed link. Runs once on mount.
  useEffect(() => {
    const token = magicTokenFromUrl();
    if (!token) return;
    let cancelled = false;

    // Strip the token from the address bar immediately so it is not left in
    // history, bookmarks, or a shared screenshot. It is single-use, but it is
    // still a credential until consumed.
    clearMagicTokenFromUrl();

    (async () => {
      try {
        const tokens = await api.consumeMagicLink(token);
        if (cancelled) return;
        setSession({ accessToken: tokens.access_token, refreshToken: tokens.refresh_token });
      } catch (error) {
        if (cancelled) return;
        setNotice({
          tone: "warn",
          text:
            error instanceof Error && error.message
              ? error.message
              : "That sign-in link is no longer valid. Request a new one below.",
        });
      } finally {
        if (!cancelled) setConsumingMagicLink(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [setSession, setNotice]);

  function selectMode(next: "login" | "register") {
    setMode(next);
    const url = new URL(window.location.href);
    url.searchParams.set("auth", next);
    window.history.replaceState({}, "", url);
  }

  const oauthSubmit = async (provider: OAuthProvider) => {
    setOauthBusy(provider);
    setNotice(null);
    try {
      const { idToken, displayName, authorizationCode, redirectUri, nonce } = await signInWithProvider(provider);
      const tokens = await api.oauthLogin(provider, idToken, displayName, authorizationCode, redirectUri, nonce);
      setSession({ accessToken: tokens.access_token, refreshToken: tokens.refresh_token });
    } catch (error) {
      setNotice({ tone: "warn", text: error instanceof Error ? error.message : "Sign-in did not complete." });
    } finally {
      setOauthBusy(null);
    }
  };

  const sendMagicLink = async () => {
    const address = (mode === "login" ? identifier : email).trim();
    if (!address) return;
    setMagicBusy(true);
    setNotice(null);
    try {
      await api.requestMagicLink(address);
      // The API answers identically whether or not the account exists, so the
      // wording here must not imply one or the other.
      setMagicSentTo(address);
    } catch (error) {
      setNotice(messageFromError(error));
    } finally {
      setMagicBusy(false);
    }
  };

  const submitMagicCode = async (event: FormEvent) => {
    event.preventDefault();
    if (!magicSentTo) return;
    setMagicBusy(true);
    setNotice(null);
    try {
      const tokens = await api.consumeMagicCode(magicSentTo, magicCode);
      setSession({ accessToken: tokens.access_token, refreshToken: tokens.refresh_token });
    } catch (error) {
      setNotice(messageFromError(error));
      setMagicCode("");
    } finally {
      setMagicBusy(false);
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setNotice(null);
    try {
      if (mode === "register") {
        await api.register({ email: email.trim() || null, phone: phone.trim() || null, password });
      }
      const loginId = mode === "register" ? email.trim() || phone.trim() : identifier.trim();
      const tokens = await api.login(loginId, password);
      if (mode === "register") {
        const version = clientConfig?.legal_document_version || "2026-07-13";
        await Promise.all([
          api.acceptLegalDocument(tokens.access_token, "privacy", version),
          api.acceptLegalDocument(tokens.access_token, "terms", version),
          api.acceptLegalDocument(tokens.access_token, "ai_disclosure", version),
        ]);
      }
      setSession({ accessToken: tokens.access_token, refreshToken: tokens.refresh_token });
    } catch (error) {
      setNotice(messageFromError(error));
    } finally {
      setBusy(false);
    }
  };

  if (consumingMagicLink) {
    return (
      <main className="auth-layout">
        <section className="auth-panel">
          <div className="auth-form-pane" style={{ alignItems: "center", textAlign: "center" }}>
            <BrandMark />
            <Loader2 className="spin" size={24} aria-hidden="true" />
            <h1>Signing you in</h1>
            <p className="inline-help">Confirming your sign-in link.</p>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="auth-layout">
      <IconButton className="auth-theme-toggle" onClick={() => toggleTheme()} aria-label={theme === "dark" ? "Appearance: dark. Switch to light." : "Appearance: light. Switch to dark."} title={theme === "dark" ? "Appearance: dark - switch to light" : "Appearance: light - switch to dark"}>
        {theme === "dark" ? <Moon size={16} /> : <Sun size={16} />}
      </IconButton>
      <section className="auth-panel auth-split">
        <aside className="auth-brand-pane">
          <a className="auth-home-link" href="/"><ArrowLeft size={15} />Home</a>
          <BrandMark />
          <p className="auth-promise">A private place for the moments, people, places, and ideas you want to remember.</p>
          <ul className="auth-trust">
            <li><ShieldCheck size={16} />Your journal stays private to your account</li>
            <li><ShieldCheck size={16} />Export or delete your data whenever you choose</li>
          </ul>
          <span className="auth-brand-dots" aria-hidden="true"><i /><i /><i /></span>
        </aside>
        <div className="auth-form-pane">
          <div className="auth-heading">
            <h1>{mode === "login" ? "Welcome back" : "Create your memory space"}</h1>
            <p>{mode === "login" ? "Return to the memory you have been building." : "Start with a private journal that becomes easier to revisit."}</p>
          </div>
          <div className="segmented" role="group" aria-label="Auth mode">
          <button aria-pressed={mode === "login"} className={mode === "login" ? "active" : ""} onClick={() => selectMode("login")} type="button">Login</button>
          <button
            aria-pressed={mode === "register"}
            className={mode === "register" ? "active" : ""}
            disabled={registrationLocked}
            onClick={() => selectMode("register")}
            type="button"
            title={registrationLocked ? "Registration is closed for this deployment" : "Register"}
          >
            Register
          </button>
        </div>
        {registrationLocked && <p className="inline-help">Registration is closed for this deployment.</p>}
        {maintenanceMessage && <div className="maintenance-banner" role="status">{maintenanceMessage}</div>}
        {notice && <NoticeBanner notice={notice} clear={() => setNotice(null)} />}
        {showOAuth && (
          <div className="auth-oauth">
            {showGoogle && (
              <button type="button" className="oauth-button oauth-google" disabled={busy || oauthBusy !== null} onClick={() => oauthSubmit("google")}>
                {oauthBusy === "google" ? <Loader2 className="spin" size={18} /> : <GoogleIcon />}
                <span>Continue with Google</span>
              </button>
            )}
            {showApple && (
              <button type="button" className="oauth-button oauth-apple" disabled={busy || oauthBusy !== null} onClick={() => oauthSubmit("apple")}>
                {oauthBusy === "apple" ? <Loader2 className="spin" size={18} /> : <AppleIcon />}
                <span>Continue with Apple</span>
              </button>
            )}
            <div className="auth-divider"><span>or {mode === "login" ? "sign in" : "sign up"} with email or phone</span></div>
          </div>
        )}
        <form className="form-stack" onSubmit={submit}>
          {mode === "login" ? (
            <label>
              Email or phone
              <input value={identifier} onChange={(event) => setIdentifier(event.target.value)} autoComplete="username" required />
            </label>
          ) : (
            <div className="two-col">
              <label>
                Email
                <input value={email} onChange={(event) => setEmail(event.target.value)} type="email" autoComplete="email" />
              </label>
              <label>
                Phone
                <input value={phone} onChange={(event) => setPhone(event.target.value)} type="tel" autoComplete="tel" />
              </label>
            </div>
          )}
          <label>
            Password
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              minLength={12}
              required
              aria-describedby={mode === "register" ? "password-requirement" : undefined}
            />
          </label>
          {mode === "register" && (
            // State the length rule before it is enforced. Left unsaid, the form
            // silently refuses to submit and the only feedback is a browser
            // tooltip that is easy to miss, which reads as the page being broken.
            <p className="inline-help" id="password-requirement">
              {password.length > 0 && password.length < 12
                ? `${12 - password.length} more character${12 - password.length === 1 ? "" : "s"} needed.`
                : "At least 12 characters. A short phrase you will remember works well."}
            </p>
          )}
          {mode === "register" && (
            <label className="auth-consent check-row">
              <input type="checkbox" checked={legalAccepted} onChange={(event) => setLegalAccepted(event.target.checked)} required />
              <span>I agree to the <a href="/terms" target="_blank" rel="noreferrer">Terms</a>, acknowledge the <a href="/privacy" target="_blank" rel="noreferrer">Privacy Policy</a>, and consent to the processing described in the <a href="/ai-disclosure" target="_blank" rel="noreferrer">AI Disclosure</a>.</span>
            </label>
          )}
          <PrimaryButton disabled={busy || !password || (mode === "register" && !legalAccepted) || (mode === "login" ? !identifier.trim() : !email.trim() && !phone.trim())}>
            <ShieldCheck size={16} />
            {mode === "login" ? "Login" : "Create Account"}
          </PrimaryButton>
        </form>
        {magicLinkEnabled && (
          <div className="auth-magic">
            {magicSentTo ? (
              <>
                <p className="inline-help" role="status">
                  If an account can be reached at <strong>{magicSentTo}</strong>, an email is on its way.
                  Click the link in it, or enter the 6-digit code below. Either works once and expires in 15 minutes.
                </p>
                <form className="form-stack" onSubmit={submitMagicCode}>
                  <label>
                    Sign-in code
                    <input
                      value={magicCode}
                      onChange={(event) => setMagicCode(event.target.value)}
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      placeholder="123456"
                      maxLength={7}
                      required
                    />
                  </label>
                  <PrimaryButton disabled={magicBusy || magicCode.replace(/\D/g, "").length !== 6}>
                    {magicBusy ? <Loader2 className="spin" size={16} /> : <ShieldCheck size={16} />}
                    Sign in with code
                  </PrimaryButton>
                </form>
                <button
                  type="button"
                  className="link-button"
                  disabled={magicBusy}
                  onClick={() => {
                    setMagicSentTo(null);
                    setMagicCode("");
                    setNotice(null);
                  }}
                >
                  Use a different email
                </button>
              </>
            ) : (
              <>
                <div className="auth-divider"><span>or sign in without a password</span></div>
                <button
                  type="button"
                  className="oauth-button"
                  disabled={busy || magicBusy || !(mode === "login" ? identifier.trim() : email.trim())}
                  onClick={sendMagicLink}
                >
                  {magicBusy ? <Loader2 className="spin" size={18} /> : <Mail size={18} />}
                  <span>Email me a sign-in link</span>
                </button>
                <p className="inline-help">
                  Enter your email above and we will send a link. No password needed.
                </p>
              </>
            )}
          </div>
        )}
          <p className="auth-policy-note">Your memories are not used to build an advertising profile. You can export your data or delete your account from Settings.</p>
        </div>
      </section>
    </main>
  );
}

function requestedAuthMode(): "login" | "register" {
  return new URLSearchParams(window.location.search).get("auth") === "register" ? "register" : "login";
}

function magicTokenFromUrl(): string | null {
  const token = new URLSearchParams(window.location.search).get("magic");
  return token && token.trim() ? token.trim() : null;
}

function clearMagicTokenFromUrl(): void {
  const url = new URL(window.location.href);
  url.searchParams.delete("magic");
  window.history.replaceState({}, "", url);
}
