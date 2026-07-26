import { useState, type FormEvent } from "react";
import { BookOpen, CheckCircle2, ExternalLink, Send, ShieldAlert, ShieldCheck, Wrench } from "lucide-react";
import { api } from "../../api";
import type { Runner } from "../../app/types";
import { STORE_GATES, STORE_TOOLS, type StoreGateStatus } from "../../app/storeReadiness";
import type { ClientConfigResponse, SafetyReportCategory } from "../../types";
import { KeyValue, Panel, PanelTitle } from "../../components/ui";

const REPORT_CATEGORIES: Array<{ value: SafetyReportCategory; label: string }> = [
  { value: "unsafe_ai_output", label: "Unsafe AI output" },
  { value: "harmful_or_illegal_content", label: "Harmful content" },
  { value: "privacy_concern", label: "Privacy concern" },
  { value: "copyright_concern", label: "Copyright concern" },
  { value: "harassment_or_abuse", label: "Harassment or abuse" },
  { value: "self_harm_or_crisis", label: "Self-harm or crisis" },
  { value: "security_concern", label: "Security concern" },
  { value: "other", label: "Other" },
];

const LEGAL_SUMMARIES = [
  {
    title: "Privacy Policy",
    body: "Thought Pins stores account data, journal entries, imported documents, memory cards, devices, and diagnostics needed to run the product. User content may be processed by configured AI, search, document, storage, and diagnostic services only to provide requested app features.",
    points: ["Export and deletion controls are built into Account.", "Private entries stay scoped to the signed-in user.", "Production builds must disclose active data categories in store consoles."],
  },
  {
    title: "Terms",
    body: "Users keep ownership of their journal and source material. They are responsible for lawful use, uploads, account security, and checking AI-assisted output before important decisions.",
    points: ["The initial release is free and contains no purchase or subscription flow.", "Thought Pins is not an emergency, medical, legal, or financial decision system.", "Accounts may be limited for abuse, unlawful content, or attempts to compromise the service."],
  },
  {
    title: "AI Disclosure",
    body: "AI features classify messages, extract memories, summarize sources, and answer from saved context. Output can be incomplete, stale, or wrong, so the app keeps safety reporting and data controls visible.",
    points: ["The app does not present AI output as human judgment.", "Users can report unsafe, harmful, private, or copyright-sensitive output.", "The client does not expose exact runtime model names."],
  },
  {
    title: "Support and Deletion",
    body: "Support, account deletion, and policy links are available before submission and should be published over HTTPS for store review. The in-app account screen also exposes export, legal acceptance, device, and deletion workflows.",
    points: ["Support contact: support@thoughtpins.com.", "Deletion removes user-scoped account data and memories.", "Review accounts should use safe seeded demo data only."],
  },
];

export function LegalView({
  clientConfig,
  token,
  run,
  localMode,
}: {
  clientConfig: ClientConfigResponse | null;
  token: string;
  run: Runner;
  localMode: boolean;
}) {
  const [category, setCategory] = useState<SafetyReportCategory>("unsafe_ai_output");
  const [summary, setSummary] = useState("");
  const [reportId, setReportId] = useState<string | null>(null);
  const canSubmit = (Boolean(token) || localMode) && summary.trim().length >= 8;

  const submitReport = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSubmit) return;
    const result = await run(
      () => api.createSafetyReport(token, {
        category,
        summary: summary.trim(),
        target_type: "general",
        source: "web",
        metadata: { surface: "legal" },
      }),
      "Safety report received",
    );
    if (result) {
      setReportId(result.id);
      setSummary("");
    }
  };

  return (
    <section className="content-grid">
      <div className="module-grid two-pane">
        <Panel>
          <PanelTitle icon={<BookOpen size={18} />} title="Legal" />
          <div className="legal-list">
            <LegalLink label="Privacy Policy" href={clientConfig?.privacy_policy_url} />
            <LegalLink label="Terms" href={clientConfig?.terms_url} />
            <LegalLink label="Support" href={clientConfig?.support_url} />
            <LegalLink label="Account Deletion" href={clientConfig?.account_deletion_url} />
            <LegalLink label="AI Disclosure" href={clientConfig?.ai_disclosure_url} />
          </div>
        </Panel>
        <Panel>
          <PanelTitle icon={<ShieldCheck size={18} />} title="App Contract" />
          <KeyValue label="API" value={clientConfig?.api_version || "unknown"} />
          <KeyValue label="Environment" value={clientConfig?.environment || "unknown"} />
          <KeyValue label="AI processing" value={clientConfig?.ai_processing || "configured"} />
          <KeyValue label="Memory context" value={clientConfig?.memory_context_mode || "unknown"} />
          <KeyValue label="Apple OAuth" value={clientConfig?.oauth_apple_enabled ? "enabled" : "disabled"} />
          <KeyValue label="Google OAuth" value={clientConfig?.oauth_google_enabled ? "enabled" : "disabled"} />
        </Panel>
      </div>
      <Panel>
        <PanelTitle icon={<BookOpen size={18} />} title="Policy Summary" />
        <div className="legal-summary-grid">
          {LEGAL_SUMMARIES.map((doc) => (
            <article className="legal-summary-card" key={doc.title}>
              <h3>{doc.title}</h3>
              <p>{doc.body}</p>
              <ul>
                {doc.points.map((point) => <li key={point}>{point}</li>)}
              </ul>
            </article>
          ))}
        </div>
      </Panel>
      <Panel>
        <PanelTitle icon={<ShieldAlert size={18} />} title="Report Safety Issue" />
        <form className="form-stack" onSubmit={submitReport}>
          <label>
            <span>Category</span>
            <select value={category} onChange={(event) => setCategory(event.target.value as SafetyReportCategory)}>
              {REPORT_CATEGORIES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
          </label>
          <label>
            <span>Summary</span>
            <textarea
              value={summary}
              maxLength={1000}
              rows={4}
              onChange={(event) => setSummary(event.target.value)}
              placeholder="Describe what happened"
            />
          </label>
          <div className="button-row">
            <button className="primary-button" type="submit" disabled={!canSubmit}>
              <Send size={16} /> Submit
            </button>
            {reportId && <small>Report {reportId} received.</small>}
          </div>
        </form>
      </Panel>
      <Panel>
        <PanelTitle icon={<ShieldCheck size={18} />} title="Store Targets" />
        <div className="store-grid">
          <KeyValue label="iOS minimum" value={clientConfig?.minimum_supported_clients.ios || "unknown"} />
          <KeyValue label="Android minimum" value={clientConfig?.minimum_supported_clients.android || "unknown"} />
          <KeyValue label="Web minimum" value={clientConfig?.minimum_supported_clients.web || "unknown"} />
          <KeyValue label="iOS store" value={clientConfig?.store_urls.ios || "not configured"} />
          <KeyValue label="Android store" value={clientConfig?.store_urls.android || "not configured"} />
          <KeyValue label="Web app" value={clientConfig?.store_urls.web || "not configured"} />
        </div>
      </Panel>
      {import.meta.env.DEV && (
        <>
          <Panel>
            <PanelTitle icon={<ShieldAlert size={18} />} title="Store Review Gate" />
            <div className="readiness-grid">
              {STORE_GATES.map((gate) => <ReadinessCard key={gate.title} gate={gate} />)}
            </div>
          </Panel>
          <Panel>
            <PanelTitle icon={<Wrench size={18} />} title="Tooling To Add" />
            <div className="tool-grid">
              {STORE_TOOLS.map((tool) => (
                <a className="tool-card" key={tool.name} href={tool.href} target="_blank" rel="noreferrer">
                  <div>
                    <strong>{tool.name}</strong>
                    <p>{tool.purpose}</p>
                    <small>{tool.whenToUse}</small>
                  </div>
                  <ExternalLink size={16} />
                </a>
              ))}
            </div>
          </Panel>
        </>
      )}
    </section>
  );
}

function ReadinessCard({ gate }: { gate: { title: string; status: StoreGateStatus; reason: string; next: string } }) {
  return (
    <article className={`readiness-card ${gate.status}`}>
      <div className="readiness-head">
        {gate.status === "ready" ? <CheckCircle2 size={17} /> : <ShieldAlert size={17} />}
        <strong>{gate.title}</strong>
        <span>{labelForStatus(gate.status)}</span>
      </div>
      <p>{gate.reason}</p>
      <small>{gate.next}</small>
    </article>
  );
}

function labelForStatus(status: StoreGateStatus): string {
  return {
    ready: "ready",
    "needs-work": "needs work",
    external: "external",
  }[status];
}

function LegalLink({ label, href }: { label: string; href?: string | null }) {
  if (!href) {
    return <div className="legal-row muted-row"><span>{label}</span><small>Not configured</small></div>;
  }
  return <a className="legal-row" href={href} target="_blank" rel="noreferrer"><span>{label}</span><ExternalLink size={16} /></a>;
}
