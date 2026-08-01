import { Check, KeyRound, Mail } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../api";
import type { Runner } from "../../app/types";
import type { SignInMethodsResponse } from "../../types";
import { Panel, PanelTitle, PrimaryButton, SecondaryButton, StatusPill } from "../../components/ui";
import "./sign-in-methods.css";

const MIN_PASSWORD_LENGTH = 12;
const PROVIDER_LABELS: Record<string, string> = { google: "Google", apple: "Apple" };

export function SignInMethodsPanel({ token, run }: { token: string; run: Runner }) {
  const [methods, setMethods] = useState<SignInMethodsResponse | null>(null);
  const [open, setOpen] = useState(false);
  const [codeSent, setCodeSent] = useState(false);
  const [code, setCode] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");

  const load = useCallback(async () => {
    const next = await run(() => api.signInMethods(token));
    if (next) setMethods(next);
  }, [run, token]);

  useEffect(() => {
    void load();
  }, [load]);

  const reset = () => {
    setOpen(false);
    setCodeSent(false);
    setCode("");
    setCurrentPassword("");
    setNewPassword("");
  };

  const needsCode = methods?.password_change_requires === "email_code";
  const unavailable = methods?.password_change_requires === "unavailable";
  const short = Math.max(0, MIN_PASSWORD_LENGTH - newPassword.length);
  const ready = !short && (needsCode ? code.trim().length >= 4 : currentPassword.length > 0);

  const sendCode = async () => {
    if (!methods?.email) return;
    const sent = await run(() => api.requestMagicLink(methods.email as string), "Code sent to your email");
    if (sent) setCodeSent(true);
  };

  const submit = async () => {
    if (!ready) return;
    const result = await run(
      () => api.setPassword(token, {
        new_password: newPassword,
        ...(needsCode ? { code: code.trim() } : { current_password: currentPassword }),
      }),
      (response) => response.other_sessions_revoked > 0
        ? `Password saved. ${response.other_sessions_revoked} other session${response.other_sessions_revoked === 1 ? "" : "s"} signed out.`
        : "Password saved",
    );
    if (!result) return;
    reset();
    await load();
  };

  return (
    <Panel className="sign-in-methods-panel">
      <PanelTitle
        icon={<KeyRound size={18} />}
        title="Sign-in methods"
        action={methods ? <StatusPill status={methods.password_set ? "password set" : "passwordless"} /> : undefined}
      />
      <p className="sign-in-lede">
        Every method below reaches this same account. Whichever one you signed up with, you can use any of the others.
      </p>

      {methods && (
        <ul className="sign-in-list">
          <MethodRow
            available={Boolean(methods.email)}
            label="Email and password"
            detail={methods.password_set ? methods.email || "" : "Not set up yet"}
            on={methods.password_set}
          />
          <MethodRow
            available={methods.magic_link_available}
            label="Emailed link or 6-digit code"
            detail={methods.magic_link_available ? methods.email || "" : "Needs an email address on the account"}
            on={methods.magic_link_available}
          />
          <MethodRow
            available
            label="Google or Apple"
            detail={methods.oauth_providers.length
              ? methods.oauth_providers.map((name) => PROVIDER_LABELS[name] || name).join(", ")
              : "No provider linked"}
            on={methods.oauth_providers.length > 0}
          />
        </ul>
      )}

      {unavailable && (
        <p className="sign-in-note">Add a verified email address before setting a password, so there is a way to confirm it is you.</p>
      )}

      {methods && !unavailable && !open && (
        <SecondaryButton type="button" onClick={() => setOpen(true)}>
          <KeyRound size={16} /> {methods.password_set ? "Change password" : "Add a password"}
        </SecondaryButton>
      )}

      {open && methods && (
        <div className="sign-in-form" role="group" aria-label={methods.password_set ? "Change password" : "Add a password"}>
          {needsCode ? (
            <>
              <p className="sign-in-note">
                This account has no password yet, so we email a fresh code first. A password outlives the browser session
                that created it, so it should take more than an open tab to add one.
              </p>
              <div className="sign-in-code-row">
                <SecondaryButton type="button" onClick={sendCode}>
                  <Mail size={16} /> {codeSent ? "Send another code" : "Email me a code"}
                </SecondaryButton>
                {codeSent && <span className="sign-in-sent">Sent to {methods.email}</span>}
              </div>
              <label>
                6-digit code
                <input
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  placeholder="123456"
                />
              </label>
            </>
          ) : (
            <label>
              Current password
              <input
                type="password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
                autoComplete="current-password"
              />
            </label>
          )}
          <label>
            New password
            <input
              type="password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              autoComplete="new-password"
            />
            <span className="field-help">
              {short ? `At least ${MIN_PASSWORD_LENGTH} characters. ${short} to go.` : "Long enough."}
            </span>
          </label>
          <div className="button-row wrap">
            <PrimaryButton type="button" disabled={!ready} onClick={submit}>
              <Check size={16} /> Save password
            </PrimaryButton>
            <SecondaryButton type="button" onClick={reset}>Cancel</SecondaryButton>
          </div>
          <p className="sign-in-note">Saving signs out your other devices, which is the usual response to a credential change.</p>
        </div>
      )}
    </Panel>
  );
}

function MethodRow({ available, label, detail, on }: { available: boolean; label: string; detail: string; on: boolean }) {
  if (!available && !on) return <li className="sign-in-row is-off"><div><strong>{label}</strong><span>{detail}</span></div></li>;
  return (
    <li className={`sign-in-row${on ? " is-on" : " is-off"}`}>
      <div><strong>{label}</strong><span>{detail}</span></div>
      {on && <Check size={16} aria-label="Available" />}
    </li>
  );
}
