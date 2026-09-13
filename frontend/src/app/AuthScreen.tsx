import { ArrowLeft, Loader2, Mail, Moon, ShieldCheck, Sun } from "lucide-react";
import type { FormEvent } from "react";
import { useEffect, useState } from "react";
import { api, type ApiSession } from "../api";
import type { Notice } from "./types";
import type { ClientConfigResponse } from "../types";
import { BrandMark, IconButton, NoticeBanner, PrimaryButton } from "../components/ui";
import { prepareAppleSignIn, setOAuthClientIds, signInWithProvider, type OAuthProvider } from "./oauth";
import { toggleTheme, useResolvedTheme } from "../core/theme";
import { PasswordField } from "../components/PasswordField";
import { useAuthRequest } from "./useAuthRequest";
import { createPasswordAuthentication } from "./passwordAuthentication";

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
  const [passwordSignIn] = useState(() => createPasswordAuthentication());
  const { pending, run: runAuth } = useAuthRequest(setSession, setNotice);
  const busy = pending !== null;
  const oauthBusy = pending === "google" || pending === "apple" ? pending : null;
  const magicBusy = pending === "email" || pending === "code";
  const [magicSentTo, setMagicSentTo] = useState<string | null>(null);
  const [magicCode, setMagicCode] = useState("");
  const consumingMagicLink = pending === "link";
  const theme = useResolvedTheme();
  const registrationLocked = clientConfig?.registration_locked ?? true;
  const showGoogle = clientConfig?.oauth_google_enabled ?? false;
  const showApple = Boolean(clientConfig?.oauth_apple_enabled && (clientConfig.oauth_apple_client_id || import.meta.env.VITE_APPLE_CLIENT_ID));
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
    if (clientConfig?.oauth_apple_enabled) prepareAppleSignIn();
  }, [clientConfig?.oauth_google_client_id, clientConfig?.oauth_apple_client_id, clientConfig?.oauth_apple_enabled]);

  function selectMode(next: "login" | "register") {
    if (busy) return;
    setMode(next);
    setNotice(null);
    const url = new URL(window.location.href);
    url.searchParams.set("auth", next);
    window.history.replaceState({}, "", url);
  }

  const complete = (tokens: { access_token: string; refresh_token: string }) => {
    setSession({ accessToken: tokens.access_token, refreshToken: tokens.refresh_token });
  };

  const oauthSubmit = (provider: OAuthProvider) => runAuth(provider, async () => {
    const { idToken, displayName, authorizationCode, redirectUri, nonce } = await signInWithProvider(provider);
    return api.oauthLogin(provider, idToken, displayName, authorizationCode, redirectUri, nonce);
  }, complete);

  const sendMagicLink = () => {
    const address = (mode === "login" ? identifier : email).trim();
    if (!address || !magicLinkEnabled) return;
    return runAuth("email", () => api.requestMagicLink(address), () => {
      setMagicSentTo(address);
      setMagicCode("");
    });
  };

  const submitMagicCode = (event: FormEvent) => {
    event.preventDefault();
    const code = magicCode.replace(/\D/g, "");
    if (!magicSentTo || code.length !== 6 || !magicLinkEnabled) return;
    return runAuth("code", () => api.consumeMagicCode(magicSentTo, code), complete, () => setMagicCode(""));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const loginId = mode === "register" ? email.trim() || phone.trim() : identifier.trim();
    if (!loginId || !password || (mode === "register" && (registrationLocked || !legalAccepted || password.length < 12))) return;
    return runAuth("password", () => passwordSignIn({
      register: mode === "register", identifier: loginId, email, phone, password,
      legalVersion: clientConfig?.legal_document_version || "2026-07-13",
    }), complete);
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
      <section className="auth-panel auth-split">
        <aside className="auth-brand-pane">
          <div className="auth-brand-nav">
            <a className="auth-home-link" href="/"><ArrowLeft size={15} />Home</a>
            <IconButton className="auth-theme-toggle" onClick={() => toggleTheme()} aria-label={theme === "dark" ? "Appearance: dark. Switch to light." : "Appearance: light. Switch to dark."} title={theme === "dark" ? "Appearance: dark - switch to light" : "Appearance: light - switch to dark"}>
              {theme === "dark" ? <Moon size={16} /> : <Sun size={16} />}
            </IconButton>
          </div>
          <BrandMark />
          <p className="auth-mobile-promise">Your memory, connected.</p>
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
          <button disabled={busy} aria-pressed={mode === "login"} className={mode === "login" ? "active" : ""} onClick={() => selectMode("login")} type="button">Login</button>
          <button
            aria-pressed={mode === "register"}
            className={mode === "register" ? "active" : ""}
            disabled={registrationLocked || busy}
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
              <button type="button" className="oauth-button oauth-google" disabled={busy} onClick={() => oauthSubmit("google")}>
                {oauthBusy === "google" ? <Loader2 className="spin" size={18} /> : <GoogleIcon />}
                <span>Continue with Google</span>
              </button>
            )}
            {showApple && (
              <button type="button" className="oauth-button oauth-apple" disabled={busy} onClick={() => oauthSubmit("apple")}>
                {oauthBusy === "apple" ? <Loader2 className="spin" size={18} /> : <AppleIcon />}
                <span>Continue with Apple</span>
              </button>
            )}
            <div className="auth-divider"><span>or {mode === "login" ? "sign in" : "sign up"} with email or phone</span></div>
          </div>
        )}
        <form className="form-stack auth-password-form" aria-busy={pending === "password"} onSubmit={submit}>
          {mode === "login" ? (
            <label>
              Email or phone
              <input disabled={busy} autoCapitalize="none" spellCheck={false} value={identifier} onChange={(event) => setIdentifier(event.target.value)} autoComplete="username" required />
            </label>
          ) : (
            <div className="two-col">
              <label>
                Email
                <input disabled={busy} autoCapitalize="none" spellCheck={false} value={email} onChange={(event) => setEmail(event.target.value)} type="email" autoComplete="email" />
              </label>
              <label>
                Phone
                <input disabled={busy} value={phone} onChange={(event) => setPhone(event.target.value)} type="tel" autoComplete="tel" />
              </label>
            </div>
          )}
          <PasswordField value={password} onChange={setPassword} disabled={busy} registering={mode === "register"} />
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
              <input type="checkbox" disabled={busy} checked={legalAccepted} onChange={(event) => setLegalAccepted(event.target.checked)} required />
              <span>I agree to the <a href="/terms" target="_blank" rel="noreferrer">Terms</a>, acknowledge the <a href="/privacy" target="_blank" rel="noreferrer">Privacy Policy</a>, and consent to the processing described in the <a href="/ai-disclosure" target="_blank" rel="noreferrer">AI Disclosure</a>.</span>
            </label>
          )}
          <PrimaryButton disabled={busy || !password || (mode === "register" && !legalAccepted) || (mode === "login" ? !identifier.trim() : !email.trim() && !phone.trim())}>
            {pending === "password" ? <Loader2 className="spin" size={16} aria-hidden="true" /> : <ShieldCheck size={16} aria-hidden="true" />}
            {mode === "login" ? "Login" : "Create Account"}
          </PrimaryButton>
        </form>
        {pending === "password" && <p className="auth-progress inline-help" role="status">{mode === "login" ? "Signing you in…" : "Creating your account…"}</p>}
        {magicLinkEnabled && (
          <div className="auth-magic">
            {magicSentTo ? (
              <>
                <p className="inline-help" role="status">
                  If an account can be reached at <strong>{magicSentTo}</strong>, an email is on its way.
                  Click the link in it, or enter the 6-digit code below. Either works once and expires in 15 minutes.
                </p>
                <form className="form-stack" aria-busy={pending === "code"} onSubmit={submitMagicCode}>
                  <label>
                    Sign-in code
                    <input
                      disabled={busy}
                      value={magicCode}
                      onChange={(event) => setMagicCode(event.target.value)}
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      placeholder="123456"
                      maxLength={7}
                      required
                    />
                  </label>
                  <PrimaryButton disabled={busy || magicCode.replace(/\D/g, "").length !== 6}>
                    {magicBusy ? <Loader2 className="spin" size={16} /> : <ShieldCheck size={16} />}
                    Sign in with code
                  </PrimaryButton>
                </form>
                <button
                  type="button"
                  className="link-button"
                  disabled={busy}
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
                  disabled={busy || !(mode === "login" ? identifier.trim() : email.trim())}
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
