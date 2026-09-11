import { useCallback, useEffect, useRef, useState } from "react";
import { api, configureApiSession, type ApiSession } from "./api";
import { AIConsentScreen } from "./app/AIConsentScreen";
import { AppShell } from "./app/AppShell";
import { AuthScreen } from "./app/AuthScreen";
import { InviteScreen } from "./app/InviteScreen";
import type { GlobalComposeMode, Notice, View } from "./app/types";
import { messageFromError } from "./app/types";
import { LoadingScreen } from "./components/ui";
import { AccountView } from "./features/account/AccountView";
import { CaptureView } from "./features/capture/CaptureView";
import { ChatView } from "./features/chat/ChatView";
import { DashboardView } from "./features/dashboard/DashboardView";
import { EntriesView } from "./features/entries/EntriesView";
import { JobsView } from "./features/jobs/JobsView";
import { LegalView } from "./features/legal/LegalView";
import { LibraryView } from "./features/library/LibraryView";
import { MemoryView } from "./features/memory/MemoryView";
import { PinsView } from "./features/pins/PinsView";
import { RecapView } from "./features/recap/RecapView";
import type { ClientConfigResponse, InviteStatusResponse, MeResponse } from "./types";

const SESSION_KEY = "thoughtpins.session.v1";

function loadSession(): ApiSession | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as ApiSession) : null;
  } catch {
    return null;
  }
}

function saveSession(session: ApiSession | null) {
  if (!session) {
    localStorage.removeItem(SESSION_KEY);
    return;
  }
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export default function App() {
  const [session, setSessionState] = useState<ApiSession | null>(() => loadSession());
  const sessionRef = useRef<ApiSession | null>(session);
  const [clientConfig, setClientConfig] = useState<ClientConfigResponse | null>(null);
  const [configLoaded, setConfigLoaded] = useState(false);
  const [me, setMe] = useState<MeResponse | null>(null);
  const [view, setView] = useState<View>("chat");
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busy, setBusy] = useState(false);
  const [composePending, setComposePending] = useState<GlobalComposeMode | null>(null);
  const [aiConsentState, setAiConsentState] = useState<"loading" | "required" | "accepted">("loading");
  const [invite, setInvite] = useState<InviteStatusResponse | null>(null);
  const [inviteState, setInviteState] = useState<"loading" | "resolved">("loading");

  const token = session?.accessToken || "";
  const localMode = configLoaded && clientConfig?.auth_required === false && !session;
  const canUseApp = Boolean(session || clientConfig?.auth_required === false);
  const maintenanceMessage = clientConfig?.maintenance_mode
    ? clientConfig.maintenance_message || "Thought Pins is in maintenance for a short upgrade. Please try again soon."
    : null;

  const setSession = useCallback((next: ApiSession | null) => {
    sessionRef.current = next;
    setSessionState(next);
    saveSession(next);
    if (!next) setMe(null);
  }, []);

  useEffect(() => {
    sessionRef.current = session;
  }, [session]);

  useEffect(() => {
    configureApiSession({ get: () => sessionRef.current, set: setSession });
    return () => configureApiSession(null);
  }, [setSession]);

  useEffect(() => {
    let mounted = true;
    api.clientConfig()
      .then((next) => { if (mounted) setClientConfig(next); })
      .catch((error) => { if (mounted) setNotice(messageFromError(error)); })
      .finally(() => { if (mounted) setConfigLoaded(true); });
    return () => { mounted = false; };
  }, []);

  const run = useCallback(async <T,>(
    task: () => Promise<T>,
    success?: string | ((result: T) => string),
  ): Promise<T | null> => {
    setBusy(true);
    try {
      const result = await task();
      const message = typeof success === "function" ? success(result) : success;
      // An explicit empty success message clears a recovered action's error
      // without adding a toast to every chat reply. Reads omit this argument.
      if (success !== undefined) setNotice(message ? { tone: "ok", text: message } : null);
      return result;
    } catch (error) {
      // A cancelled request is a choice the person made, not a failure. Let the
      // caller decide what to show instead of flashing an error notice.
      if (error instanceof DOMException && error.name === "AbortError") throw error;
      setNotice(messageFromError(error));
      return null;
    } finally {
      setBusy(false);
    }
  }, []);

  const refreshMe = useCallback(async () => {
    if (!canUseApp) return;
    const result = await run(() => api.me(token));
    if (result) setMe(result);
  }, [canUseApp, run, token]);

  useEffect(() => {
    void refreshMe();
  }, [refreshMe]);

  const legalVersion = clientConfig?.legal_document_version || "2026-07-13";
  useEffect(() => {
    let mounted = true;
    if (!configLoaded) return () => { mounted = false; };
    if (localMode) {
      setAiConsentState("accepted");
      return () => { mounted = false; };
    }
    if (!session) {
      setAiConsentState("loading");
      return () => { mounted = false; };
    }
    setAiConsentState("loading");
    api.preferences(token)
      .then((preferences) => {
        if (!mounted) return;
        const acceptance = preferences.legal_acceptances?.ai_disclosure;
        setAiConsentState(acceptance?.version === legalVersion ? "accepted" : "required");
      })
      .catch((error) => {
        if (!mounted) return;
        setNotice(messageFromError(error));
        setAiConsentState("required");
      });
    return () => { mounted = false; };
  }, [configLoaded, legalVersion, localMode, session, token]);

  // Private launch. Asked for on its own rather than folded into /v1/me so the
  // answer is never cached alongside identity, and so redeeming a code updates
  // one piece of state.
  useEffect(() => {
    let mounted = true;
    if (!configLoaded) return () => { mounted = false; };
    if (localMode || !session) {
      setInvite(null);
      setInviteState("resolved");
      return () => { mounted = false; };
    }
    setInviteState("loading");
    api.inviteStatus(token)
      .then((next) => { if (mounted) setInvite(next); })
      .catch(() => { if (mounted) setInvite(null); })
      .finally(() => { if (mounted) setInviteState("resolved"); });
    return () => { mounted = false; };
  }, [configLoaded, localMode, session, token]);

  const logout = async () => {
    if (session?.refreshToken) await run(() => api.logout(session.refreshToken));
    setSession(null);
    setInvite(null);
    setView("chat");
  };

  const acceptAIProcessing = async () => {
    const result = await run(() => api.acceptLegalDocument(token, "ai_disclosure", legalVersion));
    if (result) setAiConsentState("accepted");
  };

  const handleGlobalCompose = useCallback(async (body: string, mode: GlobalComposeMode): Promise<boolean> => {
    if (maintenanceMessage) {
      setNotice({ tone: "warn", text: maintenanceMessage });
      setView("chat");
      return false;
    }
    setComposePending(mode);
    try {
      if (mode === "journal") {
        const result = await run(() => api.ingest(token, body), "Entry saved");
        if (result?.job_id) setView("jobs");
        else if (result) setView("entries");
        return Boolean(result);
      }
      const result = await run(() => api.chat(token, {
        text: body,
        conversation_id: "main",
      }), "Sent");
      if (result) setView("chat");
      return Boolean(result);
    } finally {
      setComposePending(null);
    }
  }, [maintenanceMessage, run, token]);

  if (!configLoaded) return <LoadingScreen />;
  if (!canUseApp) return <AuthScreen clientConfig={clientConfig} setSession={setSession} notice={notice} setNotice={setNotice} />;
  if (!localMode && aiConsentState === "loading") return <LoadingScreen />;
  if (!localMode && aiConsentState === "required") {
    return <AIConsentScreen clientConfig={clientConfig} busy={busy} onAccept={acceptAIProcessing} onSignOut={logout} />;
  }
  if (!localMode && inviteState === "loading") return <LoadingScreen />;
  // Shown after consent, so the account is fully created and its details kept
  // before the wall appears. The server enforces this independently; the screen
  // exists so the person is told what is happening rather than hitting refusals.
  if (!localMode && invite && invite.invite_required && !invite.admitted) {
    return (
      <InviteScreen
        token={token}
        status={invite}
        onAdmitted={(next) => { setInvite(next); void refreshMe(); }}
        onSignOut={logout}
      />
    );
  }

  return (
    <AppShell
      view={view}
      setView={setView}
      notice={notice}
      clearNotice={() => setNotice(null)}
      me={me}
      localMode={localMode}
      busy={busy}
      composePending={composePending}
      refreshMe={refreshMe}
      logout={logout}
      maintenanceMessage={maintenanceMessage}
      onGlobalCompose={handleGlobalCompose}
    >
      {view === "chat" && <ChatView token={token} run={run} maintenanceMessage={maintenanceMessage} voiceArchiveEnabled={Boolean(clientConfig?.voice_archive_enabled)} />}
      {view === "recap" && <RecapView token={token} run={run} />}
      {view === "people" && <MemoryView token={token} run={run} initialSection="people" lockedSection />}
      {view === "places" && <MemoryView token={token} run={run} initialSection="places" lockedSection />}
      {view === "pins" && <PinsView token={token} run={run} />}
      {view === "memory" && <MemoryView token={token} run={run} />}
      {view === "capture" && <CaptureView token={token} run={run} />}
      {view === "library" && <LibraryView token={token} run={run} />}
      {view === "entries" && <EntriesView token={token} run={run} />}
      {view === "jobs" && <JobsView token={token} run={run} />}
      {view === "status" && <DashboardView token={token} run={run} />}
      {view === "account" && <AccountView token={token} me={me} run={run} logout={logout} localMode={localMode} legalVersion={legalVersion} voiceArchiveEnabled={Boolean(clientConfig?.voice_archive_enabled)} />}
      {view === "legal" && <LegalView clientConfig={clientConfig} token={token} run={run} localMode={localMode} />}
    </AppShell>
  );
}
