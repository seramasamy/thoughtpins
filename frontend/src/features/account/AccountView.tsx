import { Activity, AlertCircle, Archive, BookOpen, Download, Plus, RefreshCw, ShieldCheck, Trash2, User } from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { api } from "../../api";
import type { ScreenProps } from "../../app/types";
import type { AccountExportResponse, DeviceResponse, MeResponse, PreferencesResponse, PreferencesUpdateRequest } from "../../types";
import type { SessionResponse } from "../../types";
import { IconButton, KeyValue, Panel, SecondaryButton, StatusPill } from "../../components/ui";
import { VaultTransferPanel } from "./VaultTransferPanel";
import { VoiceArchivePanel } from "./VoiceArchivePanel";
import { applyThemeMode, THEME_MODES, useTheme, type ThemeMode } from "../../core/theme";

const WEB_INSTALL_KEY = "thoughtpins.web_installation.v1";
const THEME_LABELS: Record<ThemeMode, string> = { auto: "Auto (system)", light: "Light", dark: "Dark" };

export function AccountView({ token, me, run, logout, localMode, legalVersion, voiceArchiveEnabled }: ScreenProps & { me: MeResponse | null; logout: () => Promise<void>; localMode: boolean; legalVersion: string; voiceArchiveEnabled: boolean }) {
  const [exported, setExported] = useState<AccountExportResponse | null>(null);
  const [prefs, setPrefs] = useState<PreferencesResponse | null>(null);
  const [devices, setDevices] = useState<DeviceResponse[]>([]);
  const [sessions, setSessions] = useState<SessionResponse[]>([]);
  const [confirm, setConfirm] = useState("");
  const theme = useTheme();

  const loadSettings = useCallback(async () => {
    const [nextPrefs, nextDevices, nextSessions] = await Promise.all([
      run(() => api.preferences(token)),
      run(() => api.devices(token)),
      run(() => api.sessions(token)),
    ]);
    if (nextPrefs) setPrefs(nextPrefs);
    if (nextDevices) setDevices(nextDevices.items);
    if (nextSessions) setSessions(nextSessions.items);
  }, [run, token]);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  const updatePrefs = async (patch: PreferencesUpdateRequest) => {
    const result = await run(() => api.updatePreferences(token, patch), "Preferences saved");
    if (result) setPrefs(result);
  };

  const accept = async (document: "privacy" | "terms" | "ai_disclosure") => {
    const result = await run(() => api.acceptLegalDocument(token, document, legalVersion), "Accepted");
    if (result) setPrefs(result);
  };

  const registerWebDevice = async () => {
    const result = await run(() => api.registerDevice(token, {
      installation_id: getWebInstallationId(),
      platform: "web",
      device_name: navigator.userAgent.slice(0, 120) || "Web browser",
      app_version: "web-local",
      build_number: "local",
      locale: navigator.language,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      push_provider: null,
      notifications_enabled: prefs?.notifications_enabled || false,
      metadata: { viewport: `${window.innerWidth}x${window.innerHeight}` },
    }), "Device registered");
    if (result) void loadSettings();
  };

  const revokeDevice = async (installationId: string) => {
    const result = await run(() => api.revokeDevice(token, installationId), "Device revoked");
    if (result) void loadSettings();
  };

  const revokeSession = async (sessionId: string) => {
    const result = await run(() => api.revokeSession(token, sessionId), "Session signed out");
    if (result) void loadSettings();
  };

  const revokeOtherSessions = async () => {
    const result = await run(() => api.revokeOtherSessions(token), "Other sessions signed out");
    if (result) void loadSettings();
  };

  const doExport = async () => {
    const result = await run(() => api.exportAccount(token), "Export loaded");
    if (result) setExported(result);
  };

  const downloadVault = async () => {
    const blob = await run(() => api.downloadObsidianVault(token), "Vault downloaded");
    if (!blob) return;
    const href = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = href;
    anchor.download = `thought-pins-vault-${new Date().toISOString().slice(0, 10)}.zip`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(href);
  };

  const doDelete = async () => {
    if (localMode || confirm !== "DELETE") return;
    const result = await run(() => api.deleteAccount(token), "Account deleted");
    if (result) await logout();
  };

  return (
    <section className="content-grid account-view">
      <div className="module-grid two-pane">
        <AccountSection icon={<User size={18} />} title="Profile" detail="Mode and identity for this private space.">
          <Panel>
            <KeyValue label="Mode" value={localMode ? "local no-auth" : "authenticated"} />
            <KeyValue label="User" value={me?.id || "unknown"} />
            <KeyValue label="Email" value={me?.email || "none"} />
            <KeyValue label="Phone" value={me?.phone || "none"} />
            <KeyValue label="Auth" value={me?.auth_method || "session"} />
          </Panel>
        </AccountSection>
        <AccountSection
          icon={<ShieldCheck size={18} />}
          title="Preferences"
          detail="Appearance, response voice, and reminder defaults."
          action={<IconButton onClick={loadSettings} aria-label="Refresh settings" title="Refresh settings"><RefreshCw size={17} /></IconButton>}
        >
          <Panel>
            <div className="form-stack">
              <div className="appearance-field">
                <span>Appearance</span>
                <div className="segmented appearance-segments" role="group" aria-label="Appearance">
                  {THEME_MODES.map((mode) => <button key={mode} type="button" className={theme === mode ? "active" : ""} onClick={() => applyThemeMode(mode)} aria-pressed={theme === mode}>{THEME_LABELS[mode]}</button>)}
                </div>
              </div>
              <label>
                Response voice
                <select value={prefs?.response_style || "friendly"} onChange={(event) => updatePrefs({ response_style: event.target.value as PreferencesResponse["response_style"] })}>
                  <option value="friendly">Friendly &amp; professional</option>
                  <option value="clear">Clear &amp; concise</option>
                  <option value="mirror">Match my style</option>
                </select>
                <span className="field-help">Friendly &amp; professional is the default. Matching your style is always an explicit choice.</span>
              </label>
              <label>
                Preferred name
                <input value={prefs?.preferred_name || ""} onChange={(event) => setPrefs((current) => current ? { ...current, preferred_name: event.target.value } : current)} onBlur={(event) => updatePrefs({ preferred_name: event.target.value || null })} />
              </label>
              <div className="two-col">
                <label>
                  Timezone
                  <input value={prefs?.timezone || ""} onChange={(event) => setPrefs((current) => current ? { ...current, timezone: event.target.value } : current)} onBlur={(event) => updatePrefs({ timezone: event.target.value || null })} />
                </label>
                <label>
                  Reminder hour
                  <input type="number" min={0} max={23} value={prefs?.reminder_hour_local ?? ""} onChange={(event) => setPrefs((current) => current ? { ...current, reminder_hour_local: event.target.value ? Number(event.target.value) : null } : current)} onBlur={(event) => updatePrefs({ reminder_hour_local: event.target.value ? Number(event.target.value) : null })} />
                </label>
              </div>
              <CheckToggle label="Notifications" checked={prefs?.notifications_enabled || false} onChange={(checked) => updatePrefs({ notifications_enabled: checked })} />
              <CheckToggle label="Occasional importance prompts" checked={prefs?.importance_prompts_enabled || false} onChange={(checked) => updatePrefs({ importance_prompts_enabled: checked })} />
              <CheckToggle label="Weekly digest" checked={prefs?.weekly_digest_enabled || false} onChange={(checked) => updatePrefs({ weekly_digest_enabled: checked })} />
              <CheckToggle label="Product updates" checked={prefs?.product_updates_enabled || false} onChange={(checked) => updatePrefs({ product_updates_enabled: checked })} />
              <CheckToggle label="Use private memories in replies by default" checked={prefs?.private_entries_in_ask || false} onChange={(checked) => updatePrefs({ private_entries_in_ask: checked })} />
              <span className="field-help">Off by default. Private memories stay out of recall unless you explicitly enable them here or for a reply. This setting does not mark new messages private.</span>
            </div>
          </Panel>
        </AccountSection>
      </div>

      <div className="module-grid">
        <AccountSection
          icon={<ShieldCheck size={18} />}
          title="Sessions"
          detail="Where this account is signed in right now."
          action={sessions.length > 1 ? <SecondaryButton onClick={revokeOtherSessions}>Sign out others</SecondaryButton> : undefined}
        >
          <Panel>
            <div className="device-list">
              {sessions.map((session) => (
                <div className="device-row" key={session.id}>
                  <div>
                    <strong>{session.current ? "This session" : "Signed-in session"}</strong>
                    <span>{session.user_agent || "Unknown client"}{session.ip_address ? ` - ${session.ip_address}` : ""}</span>
                  </div>
                  <div className="row-actions">
                    <StatusPill status={session.current ? "current" : "active"} />
                    <IconButton
                      danger
                      onClick={() => revokeSession(session.id)}
                      disabled={session.current}
                      aria-label="Sign out session"
                      title={session.current ? "Use Log out for this session" : "Sign out session"}
                    >
                      <Trash2 size={16} />
                    </IconButton>
                  </div>
                </div>
              ))}
              {!sessions.length && <p className="muted account-empty">No signed-in sessions found.</p>}
            </div>
          </Panel>
        </AccountSection>
      </div>

      <div className={`module-grid${voiceArchiveEnabled ? " two-pane" : ""}`}>
        {voiceArchiveEnabled && (
          <AccountSection icon={<Archive size={18} />} title="Voice archive" detail="Encrypted recordings kept only for your account.">
            <VoiceArchivePanel token={token} run={run} />
          </AccountSection>
        )}
        <AccountSection icon={<BookOpen size={18} />} title="Legal acceptances" detail="The policy documents accepted on this account.">
          <Panel>
            <div className="button-row wrap">
              <SecondaryButton onClick={() => accept("privacy")}>Privacy</SecondaryButton>
              <SecondaryButton onClick={() => accept("terms")}>Terms</SecondaryButton>
              <SecondaryButton onClick={() => accept("ai_disclosure")}>AI Disclosure</SecondaryButton>
            </div>
            <div className="legal-list compact">
              {Object.entries(prefs?.legal_acceptances || {}).map(([key, value]) => <div className="legal-row muted-row" key={key}><span>{key}</span><small>{value.version}</small></div>)}
            </div>
          </Panel>
        </AccountSection>
      </div>

      <div className="module-grid">
        <AccountSection
          icon={<Activity size={18} />}
          title="Devices"
          detail="Browsers and devices registered to this account."
          action={<SecondaryButton onClick={registerWebDevice}><Plus size={16} /> Register Web</SecondaryButton>}
        >
          <Panel>
            <div className="device-list">
              {devices.map((device) => (
                <div className="device-row" key={device.id}>
                  <div>
                    <strong>{device.device_name || device.platform}</strong>
                    <span>{device.installation_id}</span>
                  </div>
                  <div className="row-actions">
                    <StatusPill status={device.revoked_at_utc ? "revoked" : "ok"} />
                    <IconButton danger onClick={() => revokeDevice(device.installation_id)} disabled={Boolean(device.revoked_at_utc)} aria-label="Revoke device" title="Revoke device"><Trash2 size={16} /></IconButton>
                  </div>
                </div>
              ))}
              {!devices.length && <p className="muted account-empty">No devices registered yet. Register this browser to see it here.</p>}
            </div>
          </Panel>
        </AccountSection>
      </div>

      <div className="module-grid two-pane account-data-grid">
        <AccountSection icon={<Archive size={18} />} title="Data" detail="Take your journal and memory with you.">
          <Panel>
            <div className="form-stack">
              <div className="button-row wrap">
                <SecondaryButton onClick={doExport}><Download size={16} /> Account JSON</SecondaryButton>
                <SecondaryButton onClick={downloadVault}><Download size={16} /> Obsidian Vault</SecondaryButton>
              </div>
              <VaultTransferPanel token={token} />
              {exported && <pre className="export-box">{JSON.stringify(exported, null, 2)}</pre>}
            </div>
          </Panel>
        </AccountSection>
        <AccountSection className="account-section-danger" icon={<AlertCircle size={18} />} title="Danger zone" detail="Permanent actions that cannot be undone.">
          <Panel className="danger-zone">
            <div className="form-stack">
              {localMode && <p className="inline-help">Disabled in local no-auth mode. Use authenticated production accounts for account deletion testing.</p>}
              <label>Type DELETE to confirm account deletion<input value={confirm} onChange={(event) => setConfirm(event.target.value)} /></label>
              <div>
                <button className="danger-button" onClick={doDelete} disabled={localMode || confirm !== "DELETE"}><Trash2 size={16} /> Delete</button>
              </div>
            </div>
          </Panel>
        </AccountSection>
      </div>
    </section>
  );
}

function AccountSection({ icon, title, detail, action, className = "", children }: { icon: ReactNode; title: string; detail: string; action?: ReactNode; className?: string; children: ReactNode }) {
  return (
    <section className={`account-section ${className}`.trim()}>
      <header className="account-section-head">
        <div className="account-section-title">
          {icon}
          <div>
            <h2>{title}</h2>
            <p>{detail}</p>
          </div>
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}

function CheckToggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (checked: boolean) => void }) {
  return <label className="check-row"><input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />{label}</label>;
}

function getWebInstallationId() {
  let value = localStorage.getItem(WEB_INSTALL_KEY);
  if (!value) {
    value = `web-${crypto.randomUUID()}`;
    localStorage.setItem(WEB_INSTALL_KEY, value);
  }
  return value;
}
