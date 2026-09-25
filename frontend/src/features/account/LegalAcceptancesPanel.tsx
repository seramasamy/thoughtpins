import { ExternalLink } from "lucide-react";
import type { PreferencesResponse } from "../../types";
import { SecondaryButton } from "../../components/ui";

export type LegalDocument = "privacy" | "terms" | "ai_disclosure";
export type LegalLinks = Record<LegalDocument, string>;

const DOCUMENTS: { key: LegalDocument; label: string }[] = [
  { key: "privacy", label: "Privacy Policy" },
  { key: "terms", label: "Terms" },
  { key: "ai_disclosure", label: "AI Disclosure" },
];

/** Each accepted policy opens its public page; only an outdated or missing
    acceptance offers to record the current version. */
export function LegalAcceptancesPanel({ acceptances, legalVersion, links, onAccept }: {
  acceptances: PreferencesResponse["legal_acceptances"] | undefined;
  legalVersion: string;
  links: LegalLinks;
  onAccept: (document: LegalDocument) => void;
}) {
  return (
    <div className="legal-list legal-acceptances">
      {DOCUMENTS.map(({ key, label }) => {
        const accepted = acceptances?.[key];
        const current = accepted?.version === legalVersion;
        return (
          <div className="legal-acceptance" key={key}>
            <a className="legal-row" href={links[key]} target="_blank" rel="noreferrer">
              <span>{label}</span>
              <small>{accepted ? `Accepted · ${accepted.version}` : "Not accepted yet"}</small>
              <ExternalLink size={16} aria-hidden="true" />
              <span className="visually-hidden">(opens in a new tab)</span>
            </a>
            {!current && <SecondaryButton type="button" onClick={() => onAccept(key)}>Accept {label}</SecondaryButton>}
          </div>
        );
      })}
    </div>
  );
}
