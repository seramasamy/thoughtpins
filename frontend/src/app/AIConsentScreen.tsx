import { Loader2, LogOut, ShieldCheck } from "lucide-react";
import { useState } from "react";
import type { ClientConfigResponse } from "../types";
import { BrandMark, PrimaryButton, SecondaryButton } from "../components/ui";

export function AIConsentScreen({
  clientConfig,
  busy,
  onAccept,
  onSignOut,
}: {
  clientConfig: ClientConfigResponse | null;
  busy: boolean;
  onAccept: () => Promise<void>;
  onSignOut: () => Promise<void>;
}) {
  const [confirmed, setConfirmed] = useState(false);
  const privacyUrl = clientConfig?.privacy_policy_url || "/privacy";
  const disclosureUrl = clientConfig?.ai_disclosure_url || "/ai-disclosure";

  return (
    <main className="auth-layout">
      <section className="panel auth-panel auth-consent-panel" aria-labelledby="ai-consent-title">
        <BrandMark />
        <div className="auth-heading">
          <h1 id="ai-consent-title">Before you continue</h1>
          <p>Thought Pins sends content you choose to save or discuss to configured AI services so it can organize memories and answer with context.</p>
        </div>
        <ul className="auth-consent-points">
          <li><ShieldCheck size={17} />Your content is not used to build an advertising profile.</li>
          <li><ShieldCheck size={17} />You control what you save and can export or delete your account data.</li>
        </ul>
        <label className="auth-consent check-row">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(event) => setConfirmed(event.target.checked)}
          />
          <span>
            I understand and allow this processing. Read the <a href={privacyUrl} target="_blank" rel="noreferrer">Privacy Policy</a> and <a href={disclosureUrl} target="_blank" rel="noreferrer">AI Disclosure</a>.
          </span>
        </label>
        <div className="button-row auth-consent-actions">
          <SecondaryButton type="button" disabled={busy} onClick={onSignOut}>
            <LogOut size={16} /> Sign out
          </SecondaryButton>
          <PrimaryButton type="button" disabled={!confirmed || busy} onClick={onAccept}>
            {busy ? <Loader2 className="spin" size={16} /> : <ShieldCheck size={16} />}
            Continue
          </PrimaryButton>
        </div>
      </section>
    </main>
  );
}
