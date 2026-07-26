const SESSION_KEY = "thoughtpins.web.session.v2";
const INSTALL_KEY = "thoughtpins.web.installation.v1";
const CAPTURE_DRAFTS_KEY = "thoughtpins.captureDrafts.v1";
const VIEWS = [
  ["ask", "Chat"],
  ["memory", "Memory"],
  ["capture", "Capture"],
  ["library", "Library"],
  ["entries", "Entries"],
  ["jobs", "Activity"],
  ["dashboard", "Status"],
  ["account", "Account"],
  ["legal", "Legal"],
];
const STORE_GATES = [
  ["Not a thin web wrapper", "external", "The web product loop and source-level native shells exist; final store proof still needs signed native builds and device screenshots.", "Run native device/simulator smokes and capture phone/tablet screenshots before App Store or Play Store submission."],
  ["Account deletion and export", "ready", "The backend and web app expose export, entry deletion, logout, and account deletion controls.", "Verify the same controls inside native builds before review."],
  ["Privacy and AI disclosure", "external", "Reviewed privacy, terms, support, account deletion, and AI disclosure pages are packaged and served by the app/API image.", "Publish the same pages over HTTPS at thoughtpins.com and keep store-console metadata synchronized."],
  ["Sign in with Apple parity", "external", "If Google or another third-party sign-in is offered on iOS, Apple sign-in must be ready too.", "Enable Apple OAuth before iOS public review if third-party OAuth is enabled."],
  ["Review account and live backend", "external", "Reviewers need working credentials and a stable backend.", "Create a staging review user with safe seeded demo memories."],
  ["Data safety inventory", "ready", "A machine-readable inventory covers account data, user content, identifiers, diagnostics, AI processing, deletion, and permissions.", "Copy the inventory into App Store Connect and Play Console, then keep it synchronized with production config."],
];
const STORE_TOOLS = [
  ["Playwright", "https://github.com/microsoft/playwright", "Responsive smoke tests across desktop, tablet, and mobile widths."],
  ["axe-core", "https://github.com/dequelabs/axe-core", "Accessibility checks for review-facing flows."],
  ["Capacitor", "https://github.com/ionic-team/capacitor", "Optional hybrid shell only if the app has native-grade behavior."],
  ["fastlane", "https://github.com/fastlane/fastlane", "Screenshots, signing, TestFlight, Play testing, and store metadata automation."],
];
const JOB_STATUSES = ["", "pending", "retry", "running", "completed", "failed", "dead_letter", "canceled"];
const LEGAL_SUMMARIES = [
  ["Privacy Policy", "Thought Pins stores account data, journal entries, imported documents, memory cards, devices, and diagnostics needed to run the product. User content may be processed by configured AI, search, document, storage, and diagnostic services only to provide requested app features.", ["Export and deletion controls are built into Account.", "Private entries stay scoped to the signed-in user.", "Production builds must disclose active data categories in store consoles."]],
  ["Terms", "Users keep ownership of their journal and source material. They are responsible for lawful use, uploads, account security, and checking AI-assisted output before important decisions.", ["Thought Pins is not an emergency, medical, legal, or financial decision system.", "Accounts may be limited for abuse, unlawful content, or attempts to compromise the service.", "Service availability can change during maintenance or upgrades."]],
  ["AI Disclosure", "AI features classify messages, extract memories, summarize sources, and answer from saved context. Output can be incomplete, stale, or wrong, so the app keeps safety reporting and data controls visible.", ["The app does not present AI output as human judgment.", "Users can report unsafe, harmful, private, or copyright-sensitive output.", "The client does not expose exact runtime model names."]],
  ["Support and Deletion", "Support, account deletion, and policy links are available before submission and should be published over HTTPS for store review. The in-app account screen also exposes export, legal acceptance, device, and deletion workflows.", ["Support contact: support@thoughtpins.com.", "Deletion removes user-scoped account data and memories.", "Review accounts should use safe seeded demo data only."]],
];

const state = {
  view: "ask",
  authMode: "login",
  session: loadSession(),
  config: null,
  me: null,
  notice: null,
  busy: false,
  stats: null,
  health: null,
  memorySection: "people",
  memoryQuery: "",
  memoryCards: { items: [], section: "people", sections: {}, total: 0 },
  selectedMemoryCard: null,
  entries: { items: [], page: 1, limit: 10, total: 0, has_next: false },
  captureDrafts: loadCaptureDrafts(),
  jobs: { items: [], page: 1, limit: 10, total: 0, has_next: false, status: "" },
  answer: null,
  chatMessages: [],
  chatConversationDbId: null,
  pendingActionId: null,
  sources: [],
  selectedSource: null,
  lastLibraryResult: null,
  prefs: null,
  devices: [],
  exportPayload: null,
  composerMode: "chat",
  usePrivateMemories: false,
};

const root = document.getElementById("app");

function loadSession() {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveSession(session) {
  state.session = session;
  if (session) localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  else localStorage.removeItem(SESSION_KEY);
}

function installationId() {
  let value = localStorage.getItem(INSTALL_KEY);
  if (!value) {
    value = `web-${crypto.randomUUID ? crypto.randomUUID() : Date.now()}`;
    localStorage.setItem(INSTALL_KEY, value);
  }
  return value;
}

function requestId() {
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
  return `req-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

class ApiError extends Error {
  constructor(message, status, code, id) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code || "request_failed";
    this.requestId = id || "";
  }
}

async function api(path, options = {}) {
  const id = requestId();
  const headers = {
    "Content-Type": "application/json",
    "X-Request-ID": id,
  };
  const token = options.token === undefined ? state.session?.accessToken : options.token;
  if (token) headers.Authorization = `Bearer ${token}`;

  let response;
  try {
    response = await fetch(path, {
      method: options.method || "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch {
    throw new ApiError(
      "Thought Pins is temporarily unreachable. The service may be restarting or in maintenance.",
      0,
      "network_unavailable",
      id,
    );
  }

  if (response.status === 401 && options.retry !== false && state.session?.refreshToken && path !== "/v1/auth/refresh") {
    try {
      const refreshed = await api("/v1/auth/refresh", {
        method: "POST",
        body: { refresh_token: state.session.refreshToken },
        token: null,
        retry: false,
      });
      saveSession({ accessToken: refreshed.access_token, refreshToken: refreshed.refresh_token });
      return api(path, { ...options, retry: false });
    } catch {
      saveSession(null);
      state.me = null;
    }
  }

  if (!response.ok) {
    let body = {};
    try {
      body = await response.json();
    } catch {
      body = {};
    }
    const error = body.error || {};
    throw new ApiError(
      error.message || response.statusText || "Request failed",
      response.status,
      error.code,
      error.request_id || response.headers.get("X-Request-ID") || id,
    );
  }

  if (response.status === 204) return null;
  return response.json();
}

function chatBody(text, extra = {}) {
  return {
    text,
    conversation_id: "main",
    surface: "web",
    include_private: state.usePrivateMemories,
    ...extra,
  };
}

function answerText(answer) {
  return answer?.answer || answer?.reply || "";
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error || new Error("Could not read file."));
    reader.onload = () => {
      const value = String(reader.result || "");
      resolve(value.includes(",") ? value.split(",", 2)[1] : value);
    };
    reader.readAsDataURL(file);
  });
}

function loadCaptureDrafts() {
  try {
    const raw = localStorage.getItem(CAPTURE_DRAFTS_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.sort((a, b) => String(a.createdAtUtc).localeCompare(String(b.createdAtUtc))) : [];
  } catch {
    return [];
  }
}

function writeCaptureDrafts(drafts) {
  const retained = drafts.filter((draft) => draft.status !== "synced").slice(-250);
  localStorage.setItem(CAPTURE_DRAFTS_KEY, JSON.stringify(retained));
  state.captureDrafts = retained;
  return retained;
}

function updateCaptureDraft(id, patch) {
  const now = new Date().toISOString();
  return writeCaptureDrafts(loadCaptureDrafts().map((draft) => draft.id === id ? { ...draft, ...patch, updatedAtUtc: now } : draft));
}

function queueCaptureDraft(text, status = "queued") {
  const now = new Date().toISOString();
  const draft = {
    id: crypto.randomUUID ? crypto.randomUUID() : `draft-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    text: text.trim(),
    status,
    createdAtUtc: now,
    updatedAtUtc: now,
    attemptCount: 0,
  };
  writeCaptureDrafts([...loadCaptureDrafts(), draft]);
  return draft;
}

function removeCaptureDraft(id) {
  writeCaptureDrafts(loadCaptureDrafts().filter((draft) => draft.id !== id));
  render();
}

async function syncCaptureDrafts() {
  const pending = loadCaptureDrafts().filter((draft) => ["queued", "failed"].includes(draft.status));
  let synced = 0;
  let failed = 0;
  for (const draft of pending) {
    updateCaptureDraft(draft.id, { status: "submitting", attemptCount: Number(draft.attemptCount || 0) + 1, lastError: "" });
    try {
      const result = await api("/v1/entries", { method: "POST", body: { text: draft.text } });
      updateCaptureDraft(draft.id, { status: "synced", entryId: result?.entry_id || "", jobId: result?.job_id || "" });
      synced += 1;
    } catch (error) {
      const message = error instanceof Error ? error.message : "Sync failed";
      updateCaptureDraft(draft.id, { status: "failed", lastError: message });
      failed += 1;
    }
  }
  setNotice(failed ? "warn" : "ok", `${synced} local drafts synced, ${failed} failed.`);
}
function setNotice(tone, text, requestIdValue = "") {
  state.notice = { tone, text, requestId: requestIdValue };
  render();
}

function clearNotice() {
  state.notice = null;
  render();
}

function errorNotice(error) {
  if (error instanceof ApiError) {
    setNotice(error.status >= 500 ? "error" : "warn", error.message, error.requestId);
    return;
  }
  setNotice("error", error instanceof Error ? error.message : "Unexpected error");
}

async function run(task, success) {
  state.busy = true;
  render();
  try {
    const result = await task();
    if (success) state.notice = { tone: "ok", text: success };
    return result;
  } catch (error) {
    errorNotice(error);
    return null;
  } finally {
    state.busy = false;
    render();
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function fmtDate(value) {
  if (!value) return "Unknown";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function badge(value) {
  const key = String(value || "unknown");
  return `<span class="badge ${escapeHtml(key)}">${escapeHtml(humanizeIdentifier(key))}</span>`;
}

function humanizeIdentifier(value) {
  return String(value || "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function displayReferenceTitle(path, fallback = "Memory note") {
  const leaf = String(path || "").split(/[\\/]/).pop() || "";
  const title = leaf.replace(/\.md$/i, "").trim();
  return title || fallback;
}

function sourceOriginalUrl(source) {
  const candidate = source?.canonical_url || source?.source_url || source?.original_url || "";
  try {
    const parsed = new URL(candidate);
    return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : "";
  } catch {
    return "";
  }
}

function sourcePublisher(source) {
  return source?.publisher || source?.source_domain || source?.author || humanizeIdentifier(source?.source_type || "Source");
}

function titleFor(view) {
  return VIEWS.find(([id]) => id === view)?.[1] || "Thought Pins";
}

function topbarSubtitle() {
  if (state.view === "memory") return "People, places, events, things, concepts, and projects extracted from your journal.";
  if (state.view === "library") return "Articles, books, notes, and documents you want the system to remember.";
  if (state.view === "ask") return "Primary chat surface for memory-backed conversation.";
  if (state.view === "jobs") return "Background saves, imports, retries, and failures.";
  return new Date().toLocaleDateString();
}

function loggedInOrLocal() {
  return Boolean(state.session?.accessToken || state.config?.auth_required === false);
}

async function bootstrap() {
  try {
    state.config = await api("/v1/client-config", { token: null, retry: false });
  } catch (error) {
    state.config = {
      app_name: "Thought Pins",
      api_version: "unknown",
      environment: "unknown",
      auth_required: true,
      registration_locked: true,

      ai_processing: "configured",
      privacy_policy_url: "/privacy",
      terms_url: "/terms",
      support_url: "/support",
      account_deletion_url: "/account/delete",
      ai_disclosure_url: "/ai-disclosure",
    };
    errorNotice(error);
  }

  if (loggedInOrLocal()) {
    await refreshMe(false);
    await loadDashboard(false);
    await loadChatHistory();
  }
  render();
}

async function refreshMe(showNotice = true) {
  if (!loggedInOrLocal()) return;
  const result = await run(() => api("/v1/me"), showNotice ? "Account refreshed." : "");
  if (result) state.me = result;
}

async function loadDashboard(showNotice = true) {
  if (!loggedInOrLocal()) return;
  const [stats, health] = await Promise.all([
    api("/v1/status").catch((error) => ({ __error: error })),
    api("/v1/health/deep").catch((error) => ({ __error: error })),
  ]);
  if (!stats.__error) state.stats = stats;
  if (!health.__error) state.health = health;
  if (stats.__error || health.__error) errorNotice(stats.__error || health.__error);
  else if (showNotice) state.notice = { tone: "ok", text: "Status refreshed." };
  render();
}

async function loadEntries(page = state.entries.page || 1) {
  const result = await run(() => api(`/v1/entries?page=${page}&limit=${state.entries.limit}`));
  if (result) state.entries = result;
}

async function loadJobs(page = state.jobs.page || 1) {
  const status = state.jobs.status ? `&status=${encodeURIComponent(state.jobs.status)}` : "";
  const result = await run(() => api(`/v1/jobs?page=${page}&limit=${state.jobs.limit}${status}`));
  if (result) state.jobs = { ...result, status: state.jobs.status };
}

async function loadLibrary() {
  const result = await run(() => api("/v1/library?limit=50"));
  if (result) state.sources = result;
}

async function loadChatHistory() {
  if (!loggedInOrLocal()) return;
  const conversations = await run(() => api("/v1/chat/conversations?surface=web&limit=50"));
  if (!conversations) return;
  const main = (conversations.items || []).find((item) => item.conversation_key === "web:main");
  if (!main) {
    state.chatConversationDbId = null;
    state.chatMessages = [];
    return;
  }
  state.chatConversationDbId = main.id;
  const messages = await run(() => api(`/v1/chat/conversations/${encodeURIComponent(main.id)}/messages?limit=100`));
  if (messages) state.chatMessages = messages.items || [];
}

async function loadMemoryCards(section = state.memorySection, query = state.memoryQuery) {
  state.memorySection = section;
  state.memoryQuery = query.trim();
  const suffix = state.memoryQuery ? `&q=${encodeURIComponent(state.memoryQuery)}` : "";
  const result = await run(() => api(`/v1/memory/cards?section=${encodeURIComponent(section)}&limit=48${suffix}`));
  if (result) state.memoryCards = result;
}

async function loadMemoryCardDetail(entityId) {
  const result = await run(() => api(`/v1/memory/cards/${encodeURIComponent(entityId)}`));
  if (result) state.selectedMemoryCard = result;
}

async function loadAccountData() {
  const [prefs, devices] = await Promise.all([
    api("/v1/preferences").catch((error) => ({ __error: error })),
    api("/v1/devices").catch((error) => ({ __error: error })),
  ]);
  if (!prefs.__error) {
    state.prefs = prefs;
    state.usePrivateMemories = Boolean(prefs.private_entries_in_ask);
  }
  if (!devices.__error) state.devices = devices.items || [];
  if (prefs.__error || devices.__error) errorNotice(prefs.__error || devices.__error);
  render();
}

function render() {
  if (!state.config) {
    root.innerHTML = `<main class="loading-screen"><img class="loading-mark" src="/assets/thought-pins-mark.svg?v=20260712-memory-pin-v4" alt="" width="42" height="42"><p>Loading Thought Pins...</p></main>`;
    return;
  }

  if (!loggedInOrLocal()) {
    root.innerHTML = renderAuth();
    bindAuth();
    return;
  }

  root.innerHTML = `
    <div class="shell">
      <aside class="sidebar">
        <div class="brand">
          <img class="brand-mark" src="/assets/thought-pins-mark.svg?v=20260712-memory-pin-v4" alt="" width="38" height="38">
          <div>
            <strong>Thought Pins</strong>
            <span>${escapeHtml(state.config.environment)} - ${escapeHtml(state.config.api_version)}</span>
          </div>
        </div>
        <nav class="nav-list" aria-label="Primary">
          ${VIEWS.map(([id, label]) => `
            <button class="nav-button ${state.view === id ? "active" : ""}" data-view="${id}" type="button">
              ${escapeHtml(label)}
            </button>
          `).join("")}
        </nav>
        <div class="sidebar-footer">
          <div class="identity">
            <span>${escapeHtml(state.me?.email || state.me?.phone || state.me?.display_name || "Local session")}</span>
            <small>${state.config.auth_required ? "JWT session" : "Local no-auth mode"}</small>
          </div>
          <button class="icon-button" data-action="logout" type="button" title="Sign out">Exit</button>
        </div>
      </aside>
      <main class="main">
        <header class="topbar">
          <div>
            <h1>${escapeHtml(titleFor(state.view))}</h1>
            <span class="muted">${escapeHtml(topbarSubtitle())}</span>
          </div>
          <button class="button" data-action="refresh-current" type="button" ${state.busy ? "disabled" : ""}>Refresh</button>
        </header>
        ${renderMaintenanceBanner()}
        ${renderNotice()}
        ${renderView()}
      </main>
      ${state.view === "ask" ? "" : renderBottomComposer()}
    </div>
  `;
  bindShell();
}

function renderAuth() {
  const locked = state.config.registration_locked;
  const register = state.authMode === "register";
  return `
    <main class="auth-layout">
      <section class="auth-panel">
        <div class="brand">
          <img class="brand-mark" src="/assets/thought-pins-mark.svg?v=20260712-memory-pin-v4" alt="" width="38" height="38">
          <div>
            <strong>Thought Pins</strong>
            <span>${escapeHtml(state.config.environment)} - ${escapeHtml(state.config.api_version)}</span>
          </div>
        </div>
        ${renderMaintenanceBanner()}
        ${renderNotice()}
        <div class="segment" role="tablist" aria-label="Auth mode">
          <button class="${!register ? "active" : ""}" data-auth-mode="login" type="button">Login</button>
          <button class="${register ? "active" : ""}" data-auth-mode="register" type="button" ${locked ? "disabled" : ""}>Register</button>
        </div>
        <form class="form" id="auth-form">
          ${register ? `
            <div class="two-col">
              <label>Email<input name="email" type="email" autocomplete="email" /></label>
              <label>Phone<input name="phone" type="tel" autocomplete="tel" /></label>
            </div>
          ` : `
            <label>Email or phone<input name="identifier" autocomplete="username" required /></label>
          `}
          <label>
            Password
            <input name="password" type="password" autocomplete="${register ? "new-password" : "current-password"}" minlength="12" required />
          </label>
          <button class="button primary" type="submit" ${state.busy ? "disabled" : ""}>${register ? "Create Account" : "Login"}</button>
        </form>
        ${state.config.auth_required ? "" : `
          <div class="row" style="margin-top: 12px;">
            <span class="muted">Local API auth is off.</span>
            <button class="button" data-action="continue-local" type="button">Continue locally</button>
          </div>
        `}
      </section>
    </main>
  `;
}

function renderMaintenanceBanner() {
  if (!state.config?.maintenance_mode) return "";
  return `<div class="maintenance-banner" role="status">${escapeHtml(state.config.maintenance_message || "Thought Pins is in maintenance for a short upgrade. Please try again soon.")}</div>`;
}

function renderNotice() {
  if (!state.notice) return "";
  const request = state.notice.requestId ? `<span class="muted">Request ${escapeHtml(state.notice.requestId)}</span>` : "";
  return `
    <div class="notice ${escapeHtml(state.notice.tone)}" role="status">
      <div>
        <strong>${escapeHtml(state.notice.text)}</strong>
        ${request}
      </div>
      <button class="ghost-button" data-action="clear-notice" type="button">Dismiss</button>
    </div>
  `;
}

function renderView() {
  if (state.view === "memory") return renderMemory();
  if (state.view === "capture") return renderCapture();
  if (state.view === "ask") return renderAsk();
  if (state.view === "library") return renderLibrary();
  if (state.view === "jobs") return renderJobs();
  if (state.view === "entries") return renderEntries();
  if (state.view === "account") return renderAccount();
  if (state.view === "legal") return renderLegal();
  return renderDashboard();
}

function renderDashboard() {
  const stats = state.stats || {};
  const checks = state.health?.checks || {};
  return `
    <section class="grid">
      <div class="hero-panel">
        <div>
          <span class="eyebrow">Second brain</span>
          <h2>${escapeHtml(state.me?.display_name || state.me?.email || "Your memory layer")}</h2>
          <p>Capture from chat, notes, links, or uploads, browse structured memory here, and ask from the fixed composer at the bottom.</p>
        </div>
        <div class="hero-actions">
          <button class="button primary" data-view="memory" type="button">Browse Memory</button>
          <button class="button" data-view="library" type="button">Add Sources</button>
        </div>
      </div>
      <div class="metrics">
        ${metric("Entries", stats.raw_entries)}
        ${metric("Memories", stats.memories)}
        ${metric("Entities", stats.entities)}
        ${metric("Sources", stats.sources)}
        ${metric("Processing", checks.jobs?.running || 0)}
      </div>
      <div class="split">
        <div class="panel">
          <div class="panel-title"><h2>Runtime Health</h2>${badge(state.health?.status || "unknown")}</div>
          <div class="table">
            ${healthRow("Database", checks.db)}
            ${healthRow("Redis", checks.redis)}
            ${healthRow("Worker", checks.worker)}
            ${healthRow("AI processing", checks.llm)}
            ${healthRow("Memory search", checks.vector)}
            ${healthRow("Activity", checks.jobs)}
          </div>
        </div>
        <div class="panel">
          <div class="panel-title"><h2>System</h2>${badge(state.config.maintenance_mode ? "maintenance" : "ready")}</div>
          <div class="table">
            ${kv("API version", state.config.api_version)}
            ${kv("Context mode", state.config.memory_context_mode)}
            ${kv("Vault files", stats.vault_files ?? 0)}
            ${kv("AI processing", state.config.ai_processing || "configured")}
          </div>
        </div>
      </div>
    </section>
  `;
}

function metric(label, value) {
  return `<div class="metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value ?? 0)}</strong></div>`;
}

function healthRow(label, check) {
  const status = check?.status || "unknown";
  return `<div class="kv"><span>${escapeHtml(label)}</span><div>${badge(status)}</div></div>`;
}

function kv(label, value) {
  return `<div class="kv"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value ?? "unknown")}</strong></div>`;
}

function renderMemory() {
  const sections = [
    ["people", "People"],
    ["places", "Places"],
    ["projects", "Projects"],
    ["organizations", "Orgs"],
    ["events", "Events"],
    ["things", "Things"],
    ["concepts", "Concepts"],
    ["all", "All"],
  ];
  return `
    <section class="grid">
      <div class="memory-toolbar">
        <div class="section-tabs" role="tablist" aria-label="Memory sections">
          ${sections.map(([id, label]) => `
            <button class="${state.memorySection === id ? "active" : ""}" data-memory-section="${id}" type="button">${escapeHtml(label)}</button>
          `).join("")}
        </div>
        <form class="memory-search" id="memory-search-form">
          <input name="memory_query" value="${escapeHtml(state.memoryQuery)}" placeholder="Search memory..." />
          <button class="button" type="submit">Search</button>
          <button class="ghost-button" data-action="clear-memory-search" type="button">Clear</button>
        </form>
      </div>
      <div class="memory-layout">
        <div class="card-grid">
          ${state.memoryCards.items.length ? state.memoryCards.items.map(renderMemoryCard).join("") : `
            <div class="empty wide">No ${escapeHtml(state.memorySection)} memories yet. Add journal entries or sources and refresh this tab.</div>
          `}
        </div>
        ${state.selectedMemoryCard ? renderMemoryDetail(state.selectedMemoryCard) : renderMemoryEmptyDetail()}
      </div>
    </section>
  `;
}

function renderMemoryCard(card) {
  return `
    <article class="memory-card">
      <div class="memory-card-head">
        <div>
          <span class="eyebrow">${escapeHtml(card.type)}</span>
          <h3>${escapeHtml(card.name)}</h3>
        </div>
        ${badge(card.last_seen || "new")}
      </div>
      <div class="statline" aria-label="Memory stats">
        ${statCell("MEM", card.statline?.MEM ?? card.memory_count)}
        ${statCell("MENT", card.statline?.MENT ?? card.mention_count)}
        ${statCell("REL", card.statline?.REL ?? card.relationship_count)}
        ${statCell("LAST", card.statline?.LAST ?? card.last_seen ?? "never")}
      </div>
      ${card.subtitle ? `<p class="memory-subtitle">${escapeHtml(card.subtitle)}</p>` : ""}
      <div class="memory-facts">
        ${(card.recent_memories || []).slice(0, 2).map((memory) => `
          <div><span>${escapeHtml(memory.type)}</span>${escapeHtml(memory.text)}</div>
        `).join("")}
        ${(card.relationships || []).slice(0, 3).map((relationship) => `
          <div><span>${escapeHtml(humanizeIdentifier(relationship.type))}</span>${escapeHtml(relationship.other)}</div>
        `).join("")}
      </div>
      <div class="toolbar">
        <button class="button primary" data-action="open-memory-card" data-card-id="${escapeHtml(card.id)}" type="button">Open</button>
        <button class="button" data-action="ask-about-card" data-card-name="${escapeHtml(card.name)}" data-card-prompt="${escapeHtml(card.ask_prompt || `What do you remember about ${card.name}?`)}" type="button">Ask</button>
        <button class="button" data-action="open-report" data-card-name="${escapeHtml(card.name)}" data-card-type="${escapeHtml(card.type)}" type="button">Report</button>
      </div>
    </article>
  `;
}

function statCell(label, value) {
  return `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function renderMemoryEmptyDetail() {
  return `
    <aside class="memory-detail muted-detail">
      <div class="panel-title"><h2>Memory Detail</h2></div>
      <p class="muted">Open a card to inspect all known facts, relationships, and source entries.</p>
    </aside>
  `;
}

function renderMemoryDetail(card) {
  return `
    <aside class="memory-detail">
      <div class="panel-title">
        <div>
          <span class="eyebrow">${escapeHtml(card.type)}</span>
          <h2>${escapeHtml(card.name)}</h2>
        </div>
        <button class="ghost-button" data-action="close-memory-card" type="button">Close</button>
      </div>
      <div class="statline detail-statline">
        ${statCell("MEM", card.statline?.MEM ?? card.memory_count)}
        ${statCell("MENT", card.statline?.MENT ?? card.mention_count)}
        ${statCell("REL", card.statline?.REL ?? card.relationship_count)}
        ${statCell("LAST", card.statline?.LAST ?? card.last_seen ?? "never")}
      </div>
      ${card.aliases?.length ? `<div class="tag-list">${card.aliases.map((alias) => `<span>${escapeHtml(alias)}</span>`).join("")}</div>` : ""}
      ${card.obsidian_path ? `<div class="detail-row"><span>Archive reference</span><strong>${escapeHtml(displayReferenceTitle(card.obsidian_path, card.name))}</strong></div>` : ""}
      <div class="detail-section">
        <h3>Relationships</h3>
        ${(card.relationships || []).length ? card.relationships.map((relationship) => `
          <div class="detail-row"><span>${escapeHtml(humanizeIdentifier(relationship.type))}</span><strong>${escapeHtml(relationship.other)}</strong></div>
        `).join("") : `<p class="muted">No relationships yet.</p>`}
      </div>
      <div class="detail-section">
        <h3>Facts</h3>
        ${(card.all_memories || card.recent_memories || []).length ? (card.all_memories || card.recent_memories).map((memory) => `
          <article class="detail-memory">
            <span>${escapeHtml(memory.date || memory.type)}</span>
            <p>${escapeHtml(memory.text)}</p>
          </article>
        `).join("") : `<p class="muted">No detailed memories yet.</p>`}
      </div>
      <div class="detail-section">
        <h3>Timeline</h3>
        ${(card.timeline || []).length ? card.timeline.map((item) => `
          <article class="detail-memory">
            <span>${escapeHtml(item.date || "Undated")}</span>
            <p>${escapeHtml(item.label)}</p>
          </article>
        `).join("") : `<p class="muted">No timeline yet.</p>`}
      </div>
      <div class="detail-section">
        <h3>Source Documents</h3>
        ${(card.source_documents || []).length ? card.source_documents.map((source) => `
          <article class="detail-memory">
            <span>${escapeHtml(humanizeIdentifier(source.source_type || "source"))} - ${escapeHtml(humanizeIdentifier(source.status || "unknown"))}</span>
            <p>${escapeHtml(source.title || source.source_url || "Untitled source")}</p>
          </article>
        `).join("") : `<p class="muted">No source documents linked yet.</p>`}
      </div>
      <div class="detail-section">
        <h3>Provenance</h3>
        <div class="detail-row"><span>Confidence</span><strong>${escapeHtml(card.provenance?.confidence || "unknown")}</strong></div>
        <div class="detail-row"><span>Kind</span><strong>${escapeHtml(card.provenance?.kind || card.type || "memory")}</strong></div>
      </div>
      <div class="detail-section">
        <h3>Source Entries</h3>
        ${(card.entries || []).length ? card.entries.map((entry) => `
          <article class="detail-memory">
            <span>${escapeHtml(entry.local_date || fmtDate(entry.created_at_utc))} - ${escapeHtml(entry.source)}</span>
            <p>${escapeHtml(entry.raw_text)}</p>
          </article>
        `).join("") : `<p class="muted">No source entries linked yet.</p>`}
      </div>
    </aside>
  `;
}

function renderCapture() {
  const pending = state.captureDrafts.filter((draft) => ["queued", "failed"].includes(draft.status));
  return `
    <section class="split">
      <div class="panel">
        <div class="panel-title"><h2>New Journal Entry</h2></div>
        <form class="form" id="capture-form">
          <label>Entry<textarea name="text" required maxlength="50000"></textarea></label>
          <button class="button primary" type="submit" ${state.busy ? "disabled" : ""}>Save Entry</button>
        </form>
      </div>
      <div class="panel">
        <div class="panel-title"><h2>Local Draft Queue</h2><button class="button" data-action="sync-capture-drafts" type="button" ${pending.length ? "" : "disabled"}>Sync queued</button></div>
        <p class="muted">If saving fails while offline or during maintenance, Thought Pins keeps a local queued draft here.</p>
        <div class="draft-list">
          ${state.captureDrafts.length ? state.captureDrafts.map(renderCaptureDraft).join("") : `<div class="empty">No local drafts.</div>`}
        </div>
      </div>
    </section>
  `;
}

function renderCaptureDraft(draft) {
  return `
    <article class="draft-item">
      <div class="draft-meta">
        ${badge(draft.status)}
        <span>${escapeHtml(fmtDate(draft.updatedAtUtc))}</span>
        <span>${escapeHtml(Number(draft.attemptCount || 0))} attempts</span>
        <button class="button" data-action="remove-capture-draft" data-draft-id="${escapeHtml(draft.id)}" type="button">Remove</button>
      </div>
      <p class="draft-text">${escapeHtml(draft.text)}</p>
      ${draft.lastError ? `<p class="inline-help">${escapeHtml(draft.lastError)}</p>` : ""}
    </article>
  `;
}

function renderAsk() {
  return `
    <section class="chat-layout">
      <div class="panel">
        <div class="panel-title"><h2>Chat</h2></div>
        <div class="toolbar">
          <button class="button" data-action="load-chat" type="button">Load Chat</button>
          <span class="muted">${escapeHtml(state.chatMessages.length)} messages in this view</span>
        </div>
        <div class="chat-thread" aria-live="polite">
          ${state.chatMessages.length ? state.chatMessages.map(renderChatMessage).join("") : `<div class="empty">No chat yet.</div>`}
          ${state.busy ? `<div class="typing" role="status" aria-live="polite"><span class="spinner-dot"></span>Thinking...</div>` : ""}
        </div>
        ${state.pendingActionId ? `
          <div class="confirmation-strip">
            <span>Pending confirmation</span>
            <button class="button primary" data-action="confirm-pending" type="button" ${state.busy ? "disabled" : ""}>Confirm</button>
            <button class="button" data-action="cancel-pending" type="button" ${state.busy ? "disabled" : ""}>Cancel</button>
          </div>
        ` : ""}
        <label class="check-row" title="Allow private memories to inform this reply">
          <input data-private-recall-toggle type="checkbox" ${state.usePrivateMemories ? "checked" : ""} />
          Use private memories
        </label>
        <p class="inline-help">${state.usePrivateMemories ? "Private memories may inform this reply." : "Private memories stay out of replies."}</p>
        <form class="form chat-page-composer" id="ask-form">
          <label>Message<input name="query" type="search" autocomplete="off" required ${state.busy ? "disabled" : ""} placeholder="Ask your memory, save a note, or paste a link..." /></label>
          <button class="button primary" type="submit" ${state.busy ? "disabled" : ""}>${state.busy ? "Thinking..." : "Send"}</button>
        </form>
      </div>
    </section>
  `;
}

function renderChatMessage(message) {
  const role = message.role === "assistant" ? "assistant" : "user";
  const label = role === "assistant" ? "Thought Pins" : "You";
  const meta = [message.route_type, message.status].filter(Boolean).join(" - ");
  const hint = message.metadata?.routing_hint;
  return `
    <article class="chat-message ${role}">
      <div class="chat-message-head">
        <strong>${label}</strong>
        ${meta ? `<span>${escapeHtml(meta)}</span>` : ""}
      </div>
      <div class="chat-message-text">${escapeHtml(message.text || answerText(message))}</div>
      ${hint ? `<p class="inline-help">${escapeHtml(hint)}</p>` : ""}
    </article>
  `;
}

function renderLibrary() {
  return `
    <section class="grid">
      <div class="panel">
        <div class="panel-title"><h2>Add Source</h2></div>
        <form class="form" id="library-form">
          <div class="two-col">
            <label>Type
              <select name="source_type">
                <option value="article">Article</option>
                <option value="book">Book</option>
                <option value="essay">Essay</option>
                <option value="paper">Paper</option>
                <option value="text">Text</option>
              </select>
            </label>
            <label>Title<input name="title" maxlength="512" /></label>
          </div>
          <div class="two-col">
            <label>URL<input name="url" type="url" maxlength="4000" /></label>
            <label>Author<input name="author" maxlength="255" /></label>
          </div>
          <label>Text<textarea name="text" maxlength="200000"></textarea></label>
          <div class="two-col">
            <label>File Upload<input name="file" type="file" /></label>
            <label>Destination
              <select name="destination">
                <option value="auto">Auto</option>
                <option value="library">Library</option>
                <option value="journal">Journal</option>
              </select>
            </label>
          </div>
          <button class="button primary" type="submit">Save Source</button>
        </form>
      </div>
      ${state.lastLibraryResult ? `
        <div class="panel">
          <div class="panel-title"><h2>Last Source</h2>${badge(state.lastLibraryResult.status)}</div>
          <div class="table">
            ${kv("Title", state.lastLibraryResult.title || state.lastLibraryResult.filename || state.lastLibraryResult.document_id)}
            ${kv("Destination", state.lastLibraryResult.destination || state.lastLibraryResult.source_type || "library")}
            ${kv("Status", state.lastLibraryResult.status)}
            ${kv("Extracted", state.lastLibraryResult.extracted_chars ?? state.lastLibraryResult.chunks ?? 0)}
            ${state.lastLibraryResult.error ? kv("Note", state.lastLibraryResult.error) : ""}
          </div>
        </div>
      ` : ""}
      <div class="panel">
        <div class="panel-title">
          <h2>Sources</h2>
          <button class="button" data-action="load-library" type="button">Load Sources</button>
        </div>
        <div class="stack">
          ${state.sources.length ? state.sources.map(renderSource).join("") : `<div class="empty">No sources found.</div>`}
        </div>
      </div>
      ${state.selectedSource ? renderSourceDetail(state.selectedSource) : ""}
    </section>
  `;
}

function renderSource(source) {
  return `
    <article class="job-row">
      <div class="job-head">
        <div>
          <h3>${escapeHtml(source.title || source.source_url || source.id)}</h3>
          <span class="muted">${escapeHtml(sourcePublisher(source))} - ${escapeHtml(source.chunks)} memory ${Number(source.chunks) === 1 ? "section" : "sections"}</span>
        </div>
        ${badge(source.status)}
      </div>
      <div class="toolbar">
        <span class="muted">${escapeHtml(humanizeIdentifier(source.fetch_status || source.status))}</span>
        <button class="button" data-action="open-source" data-source-id="${escapeHtml(source.id)}" type="button">Open</button>
      </div>
    </article>
  `;
}

function renderSourceDetail(source) {
  const originalUrl = sourceOriginalUrl(source);
  const topics = Array.isArray(source.topics) ? source.topics : [];
  const keyConcepts = Array.isArray(source.key_concepts) ? source.key_concepts : [];
  return `
    <div class="panel">
      <div class="panel-title"><h2>${escapeHtml(source.title || "Source detail")}</h2>${badge(source.fetch_status || source.status)}</div>
      <div class="table">
        ${kv("Publication", sourcePublisher(source))}
        ${source.author ? kv("Author", source.author) : ""}
        ${source.published_at ? kv("Published", fmtDate(source.published_at)) : ""}
        ${kv("Format", humanizeIdentifier(source.source_type || "source"))}
        ${kv("Memory sections", source.chunks ?? 0)}
      </div>
      ${source.summary ? `<p class="entry-text">${escapeHtml(source.summary)}</p>` : ""}
      ${topics.length ? `<div class="detail-section"><h3>Topics</h3><div class="tag-list">${topics.map((topic) => `<span>${escapeHtml(humanizeIdentifier(topic))}</span>`).join("")}</div></div>` : ""}
      ${keyConcepts.length ? `<div class="detail-section"><h3>Key ideas</h3><p class="entry-text">${keyConcepts.map((concept) => escapeHtml(concept)).join(" / ")}</p></div>` : ""}
      ${originalUrl ? `<a class="button" href="${escapeHtml(originalUrl)}" target="_blank" rel="noreferrer">Open original on ${escapeHtml(sourcePublisher(source))}</a>` : ""}
    </div>
  `;
}

function renderJobs() {
  return `
    <section class="grid">
      <div class="panel">
        <div class="panel-title"><h2>Activity</h2></div>
        <p class="entry-text">Background processing for saved entries, article imports, retries, and failures. Most users only need this if something is stuck.</p>
        <div class="toolbar">
          <label>Status<select id="job-status">${JOB_STATUSES.map((status) => `<option value="${escapeHtml(status)}" ${state.jobs.status === status ? "selected" : ""}>${escapeHtml(status || "all")}</option>`).join("")}</select></label>
          <button class="button" data-action="load-jobs" type="button">Load Activity</button>
        </div>
      </div>
      <div class="stack">${state.jobs.items.length ? state.jobs.items.map(renderJob).join("") : `<div class="empty">No processing activity found.</div>`}</div>
      ${pager("jobs", state.jobs)}
    </section>
  `;
}

function renderJob(job) {
  const canRetry = ["failed", "dead_letter", "retry"].includes(job.status);
  const canCancel = ["pending", "retry"].includes(job.status);
  return `
    <article class="job-row">
      <div class="job-head"><div><h3>${escapeHtml(job.id)}</h3><span class="muted">${escapeHtml(fmtDate(job.created_at_utc))}</span></div>${badge(job.status)}</div>
      ${job.error ? `<p class="entry-text">${escapeHtml(job.error)}</p>` : ""}
      <div class="toolbar">
        <span class="muted">${job.entry_id ? `Entry ${escapeHtml(job.entry_id)}` : "No entry yet"}</span>
        ${canRetry ? `<button class="button" data-action="retry-job" data-job-id="${escapeHtml(job.id)}" type="button">Retry</button>` : ""}
        ${canCancel ? `<button class="danger-button" data-action="cancel-job" data-job-id="${escapeHtml(job.id)}" type="button">Cancel</button>` : ""}
      </div>
    </article>
  `;
}

function renderEntries() {
  return `
    <section class="grid">
      <div class="panel">
        <div class="toolbar"><span class="muted">${escapeHtml(state.entries.total)} total entries</span><button class="button" data-action="load-entries" type="button">Load Entries</button></div>
      </div>
      <div class="stack">${state.entries.items.length ? state.entries.items.map(renderEntry).join("") : `<div class="empty">No entries found.</div>`}</div>
      ${pager("entries", state.entries)}
    </section>
  `;
}

function renderEntry(entry) {
  return `
    <article class="entry-card">
      <div class="entry-head"><div><h3>${escapeHtml(entry.local_date || fmtDate(entry.created_at_utc))}</h3><span class="muted">${escapeHtml(entry.source)} - ${escapeHtml(entry.sensitivity)}</span></div>${badge(entry.processed_status)}</div>
      <p class="entry-text">${escapeHtml(entry.raw_text)}</p>
      ${entry.processing_error ? `<p class="entry-text">${escapeHtml(entry.processing_error)}</p>` : ""}
      <div class="toolbar"><span class="muted">${escapeHtml(entry.id)}</span><button class="danger-button" data-action="delete-entry" data-entry-id="${escapeHtml(entry.id)}" type="button">Delete</button></div>
    </article>
  `;
}

function pager(kind, pageState) {
  return `
    <div class="toolbar">
      <button class="button" data-action="${kind}-prev" type="button" ${pageState.page <= 1 ? "disabled" : ""}>Previous</button>
      <span class="muted">Page ${escapeHtml(pageState.page)} - ${escapeHtml(pageState.limit)} per page</span>
      <button class="button" data-action="${kind}-next" type="button" ${pageState.has_next ? "" : "disabled"}>Next</button>
    </div>
  `;
}

function renderAccount() {
  const prefs = state.prefs || {};
  return `
    <section class="grid">
      <div class="split">
        <div class="panel">
          <div class="panel-title"><h2>Account</h2></div>
          <div class="table">
            ${kv("User ID", state.me?.id || "local")}
            ${kv("Email", state.me?.email || "not set")}
            ${kv("Phone", state.me?.phone || "not set")}
            ${kv("Display name", state.me?.display_name || "not set")}
            ${kv("Auth method", state.me?.auth_method || (state.config.auth_required ? "unknown" : "local"))}
          </div>
        </div>
        <div class="panel">
          <div class="panel-title"><h2>Preferences</h2></div>
          <form class="form" id="preferences-form">
            <div class="two-col">
              <label>Preferred name<input name="preferred_name" value="${escapeHtml(prefs.preferred_name || "")}" /></label>
              <label>Timezone<input name="timezone" value="${escapeHtml(prefs.timezone || "")}" /></label>
            </div>
            <label>Reminder hour<input name="reminder_hour_local" type="number" min="0" max="23" value="${escapeHtml(prefs.reminder_hour_local ?? "")}" /></label>
            <label>Response voice<select name="response_style"><option value="friendly" ${(prefs.response_style || "friendly") === "friendly" ? "selected" : ""}>Friendly &amp; professional</option><option value="clear" ${prefs.response_style === "clear" ? "selected" : ""}>Clear &amp; concise</option><option value="mirror" ${prefs.response_style === "mirror" ? "selected" : ""}>Match my style</option></select></label>
            <label class="check-row"><input name="notifications_enabled" type="checkbox" ${prefs.notifications_enabled ? "checked" : ""} />Notifications</label>
            <label class="check-row"><input name="weekly_digest_enabled" type="checkbox" ${prefs.weekly_digest_enabled ? "checked" : ""} />Weekly digest</label>
            <label class="check-row"><input name="product_updates_enabled" type="checkbox" ${prefs.product_updates_enabled ? "checked" : ""} />Product updates</label>
            <label class="check-row"><input name="private_entries_in_ask" type="checkbox" ${prefs.private_entries_in_ask ? "checked" : ""} />Use private memories in replies by default</label>
            <p class="inline-help">Off by default. Private memories stay out of recall unless you explicitly enable them.</p>
            <button class="button primary" type="submit">Save Preferences</button>
          </form>
        </div>
      </div>
      <div class="panel">
        <div class="panel-title"><h2>Devices</h2><button class="button" data-action="register-device" type="button">Register Web Device</button></div>
        <div class="stack">${state.devices.length ? state.devices.map(renderDevice).join("") : `<div class="empty">No devices found.</div>`}</div>
      </div>
      <div class="panel">
        <div class="panel-title"><h2>Legal Acceptances</h2></div>
        <div class="toolbar">
          <button class="button" data-action="accept-legal" data-document="privacy" type="button">Privacy</button>
          <button class="button" data-action="accept-legal" data-document="terms" type="button">Terms</button>
          <button class="button" data-action="accept-legal" data-document="ai_disclosure" type="button">AI Disclosure</button>
        </div>
        <div class="table" style="margin-top: 12px;">
          ${Object.entries(prefs.legal_acceptances || {}).map(([key, value]) => kv(key, value.version)).join("") || `<div class="empty">No acceptances yet.</div>`}
        </div>
      </div>
      <div class="panel">
        <div class="panel-title"><h2>Data Export</h2><button class="button" data-action="export-account" type="button">Export JSON</button></div>
        ${state.exportPayload ? `<pre>${escapeHtml(JSON.stringify(state.exportPayload, null, 2))}</pre>` : `<div class="empty">No export loaded.</div>`}
      </div>
      <div class="panel">
        <div class="panel-title"><h2>Delete Account</h2></div>
        <form class="form" id="delete-account-form">
          <label>Confirmation<input name="confirm" placeholder="DELETE" /></label>
          <button class="danger-button" type="submit">Delete Account Data</button>
        </form>
      </div>
    </section>
  `;
}

function renderDevice(device) {
  return `
    <article class="job-row">
      <div class="job-head">
        <div><h3>${escapeHtml(device.device_name || device.platform)}</h3><span class="muted">${escapeHtml(device.installation_id)}</span></div>
        ${badge(device.revoked_at_utc ? "revoked" : "ok")}
      </div>
      <div class="toolbar">
        <span class="muted">${escapeHtml(device.app_version || "unknown")} - ${escapeHtml(device.last_seen_at_utc || "never")}</span>
        <button class="danger-button" data-action="revoke-device" data-installation-id="${escapeHtml(device.installation_id)}" type="button" ${device.revoked_at_utc ? "disabled" : ""}>Revoke</button>
      </div>
    </article>
  `;
}

function renderLegal() {
  return `
    <section class="grid">
      <div class="split">
        <div class="panel">
          <div class="panel-title"><h2>Public Documents</h2></div>
          <div class="table">
            ${legalLink("Privacy Policy", state.config.privacy_policy_url)}
            ${legalLink("Terms", state.config.terms_url)}
            ${legalLink("Support", state.config.support_url)}
            ${legalLink("Account Deletion", state.config.account_deletion_url)}
            ${legalLink("AI Disclosure", state.config.ai_disclosure_url)}
          </div>
        </div>
        <div class="panel">
          <div class="panel-title"><h2>App Contract</h2></div>
          <div class="table">
            ${kv("API", state.config.api_version)}
            ${kv("Environment", state.config.environment)}
            ${kv("AI processing", state.config.ai_processing || "configured")}
            ${kv("Memory context", state.config.memory_context_mode)}
          </div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-title"><h2>Policy Summary</h2></div>
        <div class="legal-summary-grid">${LEGAL_SUMMARIES.map(renderLegalSummary).join("")}</div>
      </div>
      <div class="panel">
        <div class="panel-title"><h2>Store Review Gate</h2></div>
        <div class="readiness-grid">
          ${STORE_GATES.map(renderReadinessCard).join("")}
        </div>
      </div>
      <div class="panel">
        <div class="panel-title"><h2>Tooling To Add</h2></div>
        <div class="tool-grid">
          ${STORE_TOOLS.map(renderToolCard).join("")}
        </div>
      </div>
    </section>
  `;
}

function renderLegalSummary([title, body, points]) {
  return `
    <article class="legal-summary-card">
      <h3>${escapeHtml(title)}</h3>
      <p>${escapeHtml(body)}</p>
      <ul>${points.map((point) => `<li>${escapeHtml(point)}</li>`).join("")}</ul>
    </article>
  `;
}
function renderReadinessCard([title, status, reason, next]) {
  return `
    <article class="readiness-card ${escapeHtml(status)}">
      <div class="readiness-head"><strong>${escapeHtml(title)}</strong><span>${escapeHtml(statusLabel(status))}</span></div>
      <p>${escapeHtml(reason)}</p>
      <small>${escapeHtml(next)}</small>
    </article>
  `;
}

function renderToolCard([name, href, purpose]) {
  return `<a class="tool-card" href="${escapeHtml(href)}" target="_blank" rel="noreferrer"><strong>${escapeHtml(name)}</strong><p>${escapeHtml(purpose)}</p></a>`;
}

function statusLabel(status) {
  if (status === "needs-work") return "needs work";
  return status;
}

function renderBottomComposer() {
  const actionLabel = state.busy ? (state.composerMode === "journal" ? "Saving..." : "Thinking...") : (state.composerMode === "chat" ? "Send" : "Save");
  return `
    <form class="bottom-composer" id="bottom-composer">
      ${state.busy ? `<div class="bottom-composer-status" role="status" aria-live="polite">${state.composerMode === "journal" ? "Saving to your journal" : "Thinking with your memory"}</div>` : ""}
      <div class="composer-mode" aria-label="Composer mode">
        <button class="${state.composerMode === "chat" ? "active" : ""}" data-composer-mode="chat" type="button" ${state.busy ? "disabled" : ""}>Chat</button>
        <button class="${state.composerMode === "journal" ? "active" : ""}" data-composer-mode="journal" type="button" ${state.busy ? "disabled" : ""}>Journal</button>
      </div>
      ${state.composerMode === "chat" ? `
        <label class="check-row" title="Allow private memories to inform this reply">
          <input data-private-recall-toggle type="checkbox" ${state.usePrivateMemories ? "checked" : ""} />
          Use private memories
        </label>
      ` : ""}
      <input name="composer_text" autocomplete="off" ${state.busy ? "disabled" : ""} placeholder="${state.composerMode === "chat" ? "Ask your memory..." : "Save a journal note..."}" />
      <button class="button primary" type="submit" ${state.busy ? "disabled" : ""}>${actionLabel}</button>
    </form>
  `;
}

const GENERAL_CONFIRMATION_PHRASES = new Set(["confirm", "yes", "yes please", "do it", "proceed", "go ahead"]);
const CANCEL_CONFIRMATION_PHRASES = new Set(["cancel", "cancel that", "never mind", "nevermind", "no", "nope", "stop"]);

function confirmationIntent(text) {
  const lowered = String(text || "")
    .trim()
    .toLowerCase()
    .replace(/[?!]+/g, "")
    .replace(/[.]+$/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!lowered) return null;
  if (CANCEL_CONFIRMATION_PHRASES.has(lowered)) return "cancel";
  if (GENERAL_CONFIRMATION_PHRASES.has(lowered)) return "confirm";
  return null;
}

async function sendChatMessage(text, extra = {}) {
  if (state.config?.maintenance_mode) {
    state.chatMessages.push({
      role: "user",
      text,
      status: "sent",
      created_at_utc: new Date().toISOString(),
    });
    state.chatMessages.push({
      role: "assistant",
      text: state.config.maintenance_message || "Thought Pins is in maintenance for a short upgrade. Please try again soon.",
      route_type: "maintenance",
      status: "paused",
      created_at_utc: new Date().toISOString(),
    });
    return { status: "paused", route_type: "maintenance", reply: state.config.maintenance_message || "Maintenance currently." };
  }
  const metadata = { ...extra };
  const intent = confirmationIntent(text);
  if (state.pendingActionId && intent) {
    metadata.pending_action_id = state.pendingActionId;
    metadata.confirm_action = intent === "confirm";
  }
  state.chatMessages.push({
    role: "user",
    text,
    route_type: null,
    status: "sent",
    created_at_utc: new Date().toISOString(),
  });
  const result = await run(() => api("/v1/chat", { method: "POST", body: chatBody(text, metadata) }));
  if (!result) return null;

  state.answer = result;
  const conversationDbId = result.metadata?.conversation_db_id;
  if (conversationDbId) state.chatConversationDbId = conversationDbId;
  if (result.requires_confirmation && result.metadata?.pending_action_id) {
    state.pendingActionId = result.metadata.pending_action_id;
  } else if (metadata.pending_action_id || !result.requires_confirmation) {
    state.pendingActionId = null;
  }

  state.chatMessages.push({
    role: "assistant",
    text: answerText(result),
    route_type: result.route_type,
    status: result.status,
    entry_id: result.entry_id,
    job_id: result.job_id,
    document_id: result.document_id,
    metadata: result.metadata || {},
    created_at_utc: new Date().toISOString(),
  });
  if (state.chatMessages.length > 120) state.chatMessages = state.chatMessages.slice(-120);
  return result;
}

function legalLink(label, href) {
  if (!href) return kv(label, "not configured");
  return `<div class="kv"><span>${escapeHtml(label)}</span><a href="${escapeHtml(href)}" target="_blank" rel="noreferrer">${escapeHtml(href)}</a></div>`;
}

function bindAuth() {
  root.querySelectorAll("[data-auth-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      state.authMode = button.dataset.authMode;
      render();
    });
  });

  root.querySelector("#auth-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const password = String(data.get("password") || "");
    await run(async () => {
      let identifier = String(data.get("identifier") || "").trim();
      if (state.authMode === "register") {
        const email = String(data.get("email") || "").trim();
        const phone = String(data.get("phone") || "").trim();
        if (!email && !phone) throw new Error("Provide email or phone.");
        await api("/v1/auth/register", { method: "POST", body: { email: email || null, phone: phone || null, password }, token: null });
        identifier = email || phone;
      }
      const tokens = await api("/v1/auth/login", { method: "POST", body: { identifier, password }, token: null });
      saveSession({ accessToken: tokens.access_token, refreshToken: tokens.refresh_token });
      await refreshMe(false);
      await loadDashboard(false);
      await loadChatHistory();
    }, state.authMode === "register" ? "Account created." : "Logged in.");
  });

  root.querySelector("[data-action='continue-local']")?.addEventListener("click", async () => {
    await refreshMe(false);
    await loadDashboard(false);
    await loadChatHistory();
  });

  bindCommon();
}

function bindShell() {
  root.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.view = button.dataset.view;
      if (state.view === "dashboard" && !state.stats) await loadDashboard(false);
      if (state.view === "memory" && !state.memoryCards.items.length) await loadMemoryCards();
      if (state.view === "entries" && !state.entries.items.length) await loadEntries(1);
      if (state.view === "jobs" && !state.jobs.items.length) await loadJobs(1);
      if (state.view === "ask" && !state.chatMessages.length) await loadChatHistory();
      if (state.view === "library" && !state.sources.length) await loadLibrary();
      if (state.view === "account" && !state.prefs) await loadAccountData();
      render();
    });
  });

  root.querySelector("[data-action='logout']")?.addEventListener("click", async () => {
    if (state.session?.refreshToken) {
      await api("/v1/auth/logout", { method: "POST", body: { refresh_token: state.session.refreshToken }, token: null }).catch(() => null);
    }
    saveSession(null);
    state.me = null;
    state.notice = null;
    render();
  });

  root.querySelector("[data-action='refresh-current']")?.addEventListener("click", refreshCurrent);
  root.querySelector("[data-action='load-memory']")?.addEventListener("click", () => loadMemoryCards());
  root.querySelectorAll("[data-memory-section]").forEach((button) => {
    button.addEventListener("click", () => loadMemoryCards(button.dataset.memorySection));
  });
  root.querySelector("#memory-search-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const query = String(new FormData(event.currentTarget).get("memory_query") || "");
    loadMemoryCards(state.memorySection, query);
  });
  root.querySelector("[data-action='clear-memory-search']")?.addEventListener("click", () => loadMemoryCards(state.memorySection, ""));
  root.querySelectorAll("[data-action='open-memory-card']").forEach((button) => {
    button.addEventListener("click", () => loadMemoryCardDetail(button.dataset.cardId));
  });
  root.querySelector("[data-action='close-memory-card']")?.addEventListener("click", () => {
    state.selectedMemoryCard = null;
    render();
  });
  root.querySelectorAll("[data-composer-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      state.composerMode = button.dataset.composerMode;
      render();
    });
  });
  root.querySelectorAll("[data-private-recall-toggle]").forEach((input) => {
    input.addEventListener("change", () => {
      state.usePrivateMemories = Boolean(input.checked);
      render();
    });
  });
  root.querySelector("#bottom-composer")?.addEventListener("submit", handleBottomComposer);
  root.querySelector("[data-action='load-entries']")?.addEventListener("click", () => loadEntries(1));
  root.querySelector("[data-action='load-jobs']")?.addEventListener("click", () => {
    state.jobs.status = root.querySelector("#job-status")?.value || "";
    loadJobs(1);
  });
  root.querySelector("[data-action='load-library']")?.addEventListener("click", loadLibrary);
  root.querySelector("[data-action='load-chat']")?.addEventListener("click", loadChatHistory);
  root.querySelector("[data-action='confirm-pending']")?.addEventListener("click", async () => {
    if (!state.pendingActionId) return;
    await sendChatMessage("confirm", { pending_action_id: state.pendingActionId, confirm_action: true });
  });
  root.querySelector("[data-action='cancel-pending']")?.addEventListener("click", async () => {
    if (!state.pendingActionId) return;
    await sendChatMessage("cancel", { pending_action_id: state.pendingActionId, confirm_action: false });
  });
  root.querySelector("[data-action='entries-prev']")?.addEventListener("click", () => loadEntries(state.entries.page - 1));
  root.querySelector("[data-action='entries-next']")?.addEventListener("click", () => loadEntries(state.entries.page + 1));
  root.querySelector("[data-action='jobs-prev']")?.addEventListener("click", () => loadJobs(state.jobs.page - 1));
  root.querySelector("[data-action='jobs-next']")?.addEventListener("click", () => loadJobs(state.jobs.page + 1));

  root.querySelector("#capture-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = String(new FormData(event.currentTarget).get("text") || "").trim();
    if (!text) return;
    const result = await run(() => api("/v1/entries", { method: "POST", body: { text } }), "Entry saved.");
    if (result?.job_id) {
      event.currentTarget.reset();
      state.view = "jobs";
      await loadJobs(1);
    } else if (result) {
      event.currentTarget.reset();
      state.view = "entries";
      await loadEntries(1);
    } else {
      queueCaptureDraft(text);
      event.currentTarget.reset();
      setNotice("warn", "Saved locally. Sync queued drafts when the connection or backend is healthy.");
    }
  });

  root.querySelector("[data-action='sync-capture-drafts']")?.addEventListener("click", syncCaptureDrafts);
  root.querySelectorAll("[data-action='remove-capture-draft']").forEach((button) => {
    button.addEventListener("click", () => removeCaptureDraft(button.dataset.draftId));
  });

  root.querySelector("#ask-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const query = String(new FormData(event.currentTarget).get("query") || "").trim();
    if (!query) return;
    const result = await sendChatMessage(query);
    if (result) event.currentTarget.reset();
  });

  root.querySelector("#library-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const file = data.get("file");
    const body = {
      source_type: String(data.get("source_type") || "text"),
      title: String(data.get("title") || "").trim() || null,
      author: String(data.get("author") || "").trim() || null,
      url: String(data.get("url") || "").trim() || null,
      text: String(data.get("text") || "").trim() || null,
    };
    let result = null;
    if (file && file.name) {
      const contentBase64 = await fileToBase64(file);
      result = await run(() => api("/v1/uploads", {
        method: "POST",
        body: {
          filename: file.name,
          media_type: file.type || null,
          content_base64: contentBase64,
          destination: String(data.get("destination") || "auto"),
          caption: body.text,
          title: body.title,
          source_type: body.source_type,
          surface: "web",
          conversation_id: "uploads",
        },
      }), "File processed.");
    } else {
      if (!body.url && !body.text) {
        setNotice("warn", "Provide URL, text, or a file.");
        return;
      }
      result = await run(() => api("/v1/library", { method: "POST", body }), "Source saved.");
    }
    if (result) {
      state.lastLibraryResult = result;
      await loadLibrary();
    }
  });

  root.querySelectorAll("[data-action='open-source']").forEach((button) => {
    button.addEventListener("click", async () => {
      const result = await run(() => api(`/v1/library/${encodeURIComponent(button.dataset.sourceId)}`));
      if (result) state.selectedSource = result;
    });
  });

  root.querySelectorAll("[data-action='ask-about-card']").forEach((button) => {
    button.addEventListener("click", async () => {
      const query = button.dataset.cardPrompt || `What should I remember about ${button.dataset.cardName}?`;
      const result = await sendChatMessage(query);
      if (result) {
        state.view = "ask";
      }
    });
  });

  root.querySelectorAll("[data-action='open-report']").forEach((button) => {
    button.addEventListener("click", async () => {
      const cardType = button.dataset.cardType;
      const reportType = cardType === "person" ? "person" : cardType === "place" ? "place" : "topic";
      const result = await run(() => api(`/v1/reports?type=${encodeURIComponent(reportType)}&query=${encodeURIComponent(button.dataset.cardName)}`));
      if (result?.markdown) {
        state.answer = { answer: result.markdown, context_size_chars: result.markdown.length };
        state.chatMessages.push({
          role: "assistant",
          text: result.markdown,
          route_type: "report",
          status: "generated",
          created_at_utc: new Date().toISOString(),
        });
        state.view = "ask";
      }
    });
  });

  root.querySelectorAll("[data-action='retry-job']").forEach((button) => {
    button.addEventListener("click", async () => {
      await run(() => api(`/v1/jobs/${encodeURIComponent(button.dataset.jobId)}/retry`, { method: "POST" }), "Processing retry queued.");
      await loadJobs(state.jobs.page);
    });
  });

  root.querySelectorAll("[data-action='cancel-job']").forEach((button) => {
    button.addEventListener("click", async () => {
      await run(() => api(`/v1/jobs/${encodeURIComponent(button.dataset.jobId)}/cancel`, { method: "POST" }), "Processing canceled.");
      await loadJobs(state.jobs.page);
    });
  });

  root.querySelectorAll("[data-action='delete-entry']").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!window.confirm("Delete this entry?")) return;
      await run(() => api(`/v1/entries/${encodeURIComponent(button.dataset.entryId)}`, { method: "DELETE" }), "Entry deleted.");
      await loadEntries(state.entries.page);
    });
  });

  root.querySelector("#preferences-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const hour = String(data.get("reminder_hour_local") || "").trim();
    const body = {
      preferred_name: String(data.get("preferred_name") || "").trim() || null,
      timezone: String(data.get("timezone") || "").trim() || null,
      reminder_hour_local: hour ? Number(hour) : null,
      notifications_enabled: data.has("notifications_enabled"),
      weekly_digest_enabled: data.has("weekly_digest_enabled"),
      product_updates_enabled: data.has("product_updates_enabled"),
      private_entries_in_ask: data.has("private_entries_in_ask"),
      response_style: String(data.get("response_style") || "friendly"),
    };
    const result = await run(() => api("/v1/preferences", { method: "PATCH", body }), "Preferences saved.");
    if (result) {
      state.prefs = result;
      state.usePrivateMemories = Boolean(result.private_entries_in_ask);
    }
  });

  root.querySelector("[data-action='register-device']")?.addEventListener("click", async () => {
    const result = await run(() => api("/v1/devices", {
      method: "POST",
      body: {
        installation_id: installationId(),
        platform: "web",
        device_name: navigator.userAgent.slice(0, 120) || "Web browser",
        app_version: "web-local",
        build_number: "local",
        locale: navigator.language,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        push_provider: null,
        notifications_enabled: Boolean(state.prefs?.notifications_enabled),
        metadata: { viewport: `${window.innerWidth}x${window.innerHeight}` },
      },
    }), "Device registered.");
    if (result) await loadAccountData();
  });

  root.querySelectorAll("[data-action='revoke-device']").forEach((button) => {
    button.addEventListener("click", async () => {
      await run(() => api(`/v1/devices/${encodeURIComponent(button.dataset.installationId)}`, { method: "DELETE" }), "Device revoked.");
      await loadAccountData();
    });
  });

  root.querySelectorAll("[data-action='accept-legal']").forEach((button) => {
    button.addEventListener("click", async () => {
      const result = await run(() => api("/v1/legal/acceptances", {
        method: "POST",
        body: { document: button.dataset.document, version: "local-web-v1" },
      }), "Accepted.");
      if (result) state.prefs = result;
    });
  });

  root.querySelector("[data-action='export-account']")?.addEventListener("click", async () => {
    const result = await run(() => api("/v1/export"), "Export loaded.");
    if (result) state.exportPayload = result;
  });

  root.querySelector("#delete-account-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const confirmValue = String(new FormData(event.currentTarget).get("confirm") || "");
    if (confirmValue !== "DELETE") {
      setNotice("warn", "Confirmation must equal DELETE.");
      return;
    }
    if (!window.confirm("Delete all account data?")) return;
    await run(() => api("/v1/me", { method: "DELETE", body: { confirm: "DELETE" } }), "Account data deleted.");
    saveSession(null);
    state.me = null;
    render();
  });

  bindCommon();
}

function bindCommon() {
  root.querySelectorAll("[data-action='clear-notice']").forEach((button) => {
    button.addEventListener("click", clearNotice);
  });
}

async function handleBottomComposer(event) {
  event.preventDefault();
  const text = String(new FormData(event.currentTarget).get("composer_text") || "").trim();
  if (!text) return;
  if (state.composerMode === "journal") {
    const result = await sendChatMessage(`journal: ${text}`);
    if (result?.job_id) {
      state.view = "jobs";
      await loadJobs(1);
    } else if (result) {
      event.currentTarget.reset();
      state.view = "entries";
      await loadEntries(1);
    }
    return;
  }
  const result = await sendChatMessage(text);
  if (result) {
    event.currentTarget.reset();
    state.view = "ask";
  }
}

async function refreshCurrent() {
  if (state.view === "dashboard") return loadDashboard();
  if (state.view === "memory") return loadMemoryCards();
  if (state.view === "entries") return loadEntries(state.entries.page);
  if (state.view === "jobs") return loadJobs(state.jobs.page);
  if (state.view === "ask") return loadChatHistory();
  if (state.view === "library") return loadLibrary();
  if (state.view === "account") {
    await refreshMe(false);
    return loadAccountData();
  }
  render();
}

void bootstrap();
