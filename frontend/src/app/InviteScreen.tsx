import { ArrowRight, Check, Loader2, LogOut, Mail, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../api";
import type { ClientConfigResponse, InviteStatusResponse } from "../types";
import { BrandMark, PrimaryButton, SecondaryButton } from "../components/ui";
import "./invite-screen.css";

const CODE_LENGTH = 12;

export function InviteScreen({
  token,
  clientConfig,
  status,
  onAdmitted,
  onSignOut,
}: {
  token: string;
  clientConfig: ClientConfigResponse | null;
  status: InviteStatusResponse | null;
  onAdmitted: (next: InviteStatusResponse) => void;
  onSignOut: () => Promise<void>;
}) {
  const [code, setCode] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showRequest, setShowRequest] = useState(false);

  const contact = status?.contact_email || clientConfig?.invite_request_email || "invite@thoughtpins.com";
  const normalized = useMemo(() => code.toUpperCase().replace(/[^A-Z0-9]/g, ""), [code]);
  const ready = normalized.length >= 4 && !busy;
  const locked = (status?.attempts_remaining ?? 1) <= 0;

  const mailto = useMemo(() => {
    const subject = "Thought Pins invite request";
    const body = note.trim()
      ? `${note.trim()}\n\n— sent from the Thought Pins private launch page`
      : "I would like an invite code for Thought Pins.";
    return `mailto:${contact}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  }, [contact, note]);

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
              ? "Too many attempts on this account. Email us and we will sort it out."
              : `${normalized.length}/${CODE_LENGTH} characters. Dashes and spacing do not matter.`}
          </span>
          {error && <p className="invite-error" role="alert">{error}</p>}
        </form>

        <div className="invite-divider" role="separator"><span>or</span></div>

        {!showRequest ? (
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
            <a className="invite-mail-button" href={mailto}>
              <Mail size={16} /> Email {contact}
            </a>
            <span className="invite-help">
              This opens your email app with the message ready. Nothing is sent from this page.
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
