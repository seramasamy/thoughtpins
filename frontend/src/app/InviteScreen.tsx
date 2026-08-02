import { ArrowRight, Check, Loader2, LogOut, Mail, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../api";
import type { InviteStatusResponse } from "../types";
import { BrandMark, PrimaryButton, SecondaryButton } from "../components/ui";
import "./invite-screen.css";

const CODE_LENGTH = 12;

export function InviteScreen({
  token,
  status,
  onAdmitted,
  onSignOut,
}: {
  token: string;
  status: InviteStatusResponse | null;
  onAdmitted: (next: InviteStatusResponse) => void;
  onSignOut: () => Promise<void>;
}) {
  const [code, setCode] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showRequest, setShowRequest] = useState(false);
  const [requested, setRequested] = useState(false);

  const normalized = useMemo(() => code.toUpperCase().replace(/[^A-Z0-9]/g, ""), [code]);
  const ready = normalized.length >= 4 && !busy;
  const locked = (status?.attempts_remaining ?? 1) <= 0;

  const askForInvite = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.requestInvite(token, note.trim());
      setRequested(true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not send that just now.");
    } finally {
      setBusy(false);
    }
  };

  const submit = async () => {
    if (!ready) return;
    setBusy(true);
    setError(null);
    try {
      const next = await api.redeemInvite(token, normalized);
      if (next.admitted) {
        onAdmitted(next);
        return;
      }
      setError("That code is not valid.");
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "That code is not valid.";
      setError(message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="auth-layout invite-layout">
      <div className="invite-aurora" aria-hidden="true">
        <span /><span /><span />
      </div>

      <section className="panel invite-panel" aria-labelledby="invite-title">
        <BrandMark />

        <p className="invite-badge">
          <Sparkles size={13} aria-hidden="true" />
          Private testing
        </p>

        <div className="invite-heading">
          <h1 id="invite-title">
            Thought Pins is still<br />
            <em>rolling out quietly.</em>
          </h1>
          <p>
            Your account is saved and waiting. Enter the invite code you were sent to open it, or ask for one
            and we will get back to you.
          </p>
        </div>

        <form
          className="invite-form"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <label htmlFor="invite-code">Invite code</label>
          <div className="invite-code-row">
            <input
              id="invite-code"
              className="invite-code-input"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              placeholder="ABCD-EFGH-JKLM"
              autoComplete="one-time-code"
              autoCapitalize="characters"
              spellCheck={false}
              maxLength={32}
              aria-describedby="invite-code-help"
              disabled={locked}
            />
            <PrimaryButton type="submit" disabled={!ready || locked} aria-label="Continue">
              {busy ? <Loader2 className="spin" size={16} /> : <ArrowRight size={16} />}
            </PrimaryButton>
          </div>
          <span className="invite-help" id="invite-code-help">
            {locked
              ? "Too many attempts on this account. Request an invite below and we will sort it out."
              : `${normalized.length}/${CODE_LENGTH} characters. Dashes and spacing do not matter.`}
          </span>
          {error && <p className="invite-error" role="alert">{error}</p>}
        </form>

        <div className="invite-divider" role="separator"><span>or</span></div>

        {requested ? (
          <div className="invite-request invite-requested" role="status">
            <p className="invite-requested-title">
              <Check size={16} aria-hidden="true" /> You&apos;re on the list
            </p>
            <span className="invite-help">
              We have your request and your account is held for you. You&apos;ll get a code by email when a
              place opens up. Asking again won&apos;t move you up, so there&apos;s nothing else to do.
            </span>
          </div>
        ) : !showRequest ? (
          <SecondaryButton type="button" className="invite-request-open" onClick={() => setShowRequest(true)}>
            <Mail size={16} /> I don&apos;t have a code
          </SecondaryButton>
        ) : (
          <div className="invite-request">
            <label htmlFor="invite-note">
              Add a note <span className="invite-optional">optional</span>
            </label>
            <textarea
              id="invite-note"
              value={note}
              onChange={(event) => setNote(event.target.value)}
              rows={3}
              maxLength={600}
              placeholder="A line about what you would use it for, if you like."
            />
            <PrimaryButton type="button" className="invite-request-send" disabled={busy} onClick={() => void askForInvite()}>
              {busy ? <Loader2 className="spin" size={16} /> : <Mail size={16} />} Request an invite
            </PrimaryButton>
            <span className="invite-help">
              Sent straight to us from here — no email app needed. The note is optional.
            </span>
          </div>
        )}

        <footer className="invite-footer">
          <button type="button" className="invite-signout" onClick={() => void onSignOut()}>
            <LogOut size={14} /> Sign out
          </button>
          <span className="invite-saved">
            <Check size={13} aria-hidden="true" /> Your details are saved
          </span>
        </footer>
      </section>
    </main>
  );
}
