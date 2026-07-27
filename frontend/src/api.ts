import type {
  AccountExportResponse,
  AskResponse,
  ApiErrorBody,
  ChatConversationsPageResponse,
  ChatMessagesPageResponse,
  ChatRequest,
  ChatResponse,
  ClientConfigResponse,
  DeepHealthResponse,
  DeviceRegistrationRequest,
  DeviceResponse,
  DevicesPageResponse,
  EntriesPageResponse,
  EntryResponse,
  IngestResponse,
  JobsPageResponse,
  JobResponse,
  LegalDocument,
  LibraryIngestRequest,
  LibraryIngestResponse,
  LibrarySourceResponse,
  MemoryCardDetailResponse,
  MemoryCardsResponse,
  MeResponse,
  PreferencesResponse,
  PreferencesUpdateRequest,
  ReportResponse,
  SafetyReportRequest,
  SafetyReportResponse,
  SessionResponse,
  SessionsPageResponse,
  StatsResponse,
  TokenResponse,
  UploadDestination,
  UploadIngestResponse,
  VaultConflictPolicy,
  VaultImportMode,
  VaultImportResponse,
  VaultImportSessionResponse,
  VoiceArchiveConsentRequest,
  VoiceArchiveDeleteResponse,
  VoiceArchiveStatusResponse,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";

export class ApiError extends Error {
  status: number;
  code: string;
  requestId: string;

  constructor(message: string, status: number, code = "request_failed", requestId = "") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

export type ApiSession = {
  accessToken: string;
  refreshToken: string;
};

type SessionAccess = {
  get: () => ApiSession | null;
  set: (session: ApiSession | null) => void;
};

let sessionAccess: SessionAccess | null = null;

export function configureApiSession(access: SessionAccess | null) {
  sessionAccess = access;
}

type RequestOptions = {
  token?: string | null;
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
  skipAuthRefresh?: boolean;
  idempotencyKey?: string;
};

async function send(path: string, options: RequestOptions, token: string | null) {
  const requestId = crypto.randomUUID();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Request-ID": requestId,
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  if (options.idempotencyKey) {
    headers["Idempotency-Key"] = options.idempotencyKey;
  }

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: options.method || "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    });
    return { requestId, response };
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new ApiError(
      "Thought Pins is temporarily unreachable. The service may be restarting or in maintenance.",
      0,
      "network_unavailable",
      requestId,
    );
  }
}

async function parseResponse<T>(response: Response, requestId: string): Promise<T> {
  if (response.status === 204) {
    return undefined as T;
  }

  if (!response.ok) {
    let body: ApiErrorBody = {};
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      body = {};
    }
    const error = body.error;
    throw new ApiError(
      error?.message || response.statusText || "Request failed",
      response.status,
      error?.code || "request_failed",
      error?.request_id || response.headers.get("X-Request-ID") || requestId,
    );
  }

  return (await response.json()) as T;
}

async function refreshSession(): Promise<ApiSession | null> {
  const current = sessionAccess?.get();
  if (!current?.refreshToken) {
    return null;
  }
  const tokens = await request<TokenResponse>("/v1/auth/refresh", {
    method: "POST",
    token: null,
    skipAuthRefresh: true,
    body: { refresh_token: current.refreshToken },
  });
  const next = { accessToken: tokens.access_token, refreshToken: tokens.refresh_token };
  sessionAccess?.set(next);
  return next;
}

async function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error || new Error("Could not read file"));
    reader.onload = () => {
      const value = String(reader.result || "");
      resolve(value.includes(",") ? value.split(",", 2)[1] : value);
    };
    reader.readAsDataURL(blob);
  });
}

async function sha256Hex(blob: Blob): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await blob.arrayBuffer());
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = (options.method || "GET").toUpperCase();
  const prepared = {
    ...options,
    idempotencyKey:
      options.idempotencyKey || (["POST", "PUT", "PATCH", "DELETE"].includes(method) ? crypto.randomUUID() : undefined),
  };
  let token = prepared.token !== undefined ? prepared.token : sessionAccess?.get()?.accessToken || null;
  let attempt = await send(path, prepared, token);

  if (attempt.response.status === 401 && !prepared.skipAuthRefresh) {
    try {
      const refreshed = await refreshSession();
      if (refreshed?.accessToken) {
        token = refreshed.accessToken;
        attempt = await send(path, prepared, token);
      }
    } catch {
      sessionAccess?.set(null);
    }
  }

  return parseResponse<T>(attempt.response, attempt.requestId);
}

async function requestBlob(path: string, options: RequestOptions = {}): Promise<Blob> {
  let token = options.token !== undefined ? options.token : sessionAccess?.get()?.accessToken || null;
  let attempt = await send(path, options, token);

  if (attempt.response.status === 401 && !options.skipAuthRefresh) {
    try {
      const refreshed = await refreshSession();
      if (refreshed?.accessToken) {
        token = refreshed.accessToken;
        attempt = await send(path, options, token);
      }
    } catch {
      sessionAccess?.set(null);
    }
  }
  if (!attempt.response.ok) {
    await parseResponse<never>(attempt.response, attempt.requestId);
    throw new ApiError("Request failed", attempt.response.status, "request_failed", attempt.requestId);
  }
  return attempt.response.blob();
}

export const api = {
  baseUrl: API_BASE_URL,
  clientConfig() {
    return request<ClientConfigResponse>("/v1/client-config", { token: null });
  },
  register(body: { email?: string | null; phone?: string | null; password: string }) {
    return request<{ status: string; user_id: string; api_key: string | null }>("/v1/auth/register", {
      method: "POST",
      body,
    });
  },
  oauthLogin(
    provider: "google" | "apple",
    idToken: string,
    displayName?: string,
    authorizationCode?: string,
    redirectUri?: string,
    nonce?: string,
  ) {
    return request<TokenResponse>("/v1/auth/oauth", {
      method: "POST",
      body: {
        provider,
        id_token: idToken,
        authorization_code: authorizationCode || null,
        redirect_uri: redirectUri || null,
        nonce: nonce || null,
        display_name: displayName || null,
      },
    });
  },
  login(identifier: string, password: string) {
    return request<TokenResponse>("/v1/auth/login", {
      method: "POST",
      body: { identifier, password },
    });
  },
  requestMagicLink(email: string) {
    return request<{ status: string }>("/v1/auth/magic-link/request", {
      method: "POST",
      body: { email },
    });
  },
  consumeMagicLink(token: string) {
    return request<TokenResponse>("/v1/auth/magic-link/consume", {
      method: "POST",
      body: { token },
    });
  },
  consumeMagicCode(email: string, code: string) {
    return request<TokenResponse>("/v1/auth/magic-code/consume", {
      method: "POST",
      body: { email, code },
    });
  },
  refresh(refreshToken: string) {
    return request<TokenResponse>("/v1/auth/refresh", {
      method: "POST",
      body: { refresh_token: refreshToken },
    });
  },
  logout(refreshToken: string) {
    return request<{ status: string }>("/v1/auth/logout", {
      method: "POST",
      body: { refresh_token: refreshToken },
    });
  },
  me(token: string) {
    return request<MeResponse>("/v1/me", { token });
  },
  chat(token: string, body: ChatRequest) {
    const messageId = body.message_id || crypto.randomUUID();
    return request<ChatResponse>("/v1/chat", {
      method: "POST",
      token,
      body: { surface: "web", conversation_id: "main", ...body, message_id: messageId },
      idempotencyKey: messageId,
    });
  },
  chatConversations(token: string, page = 1, limit = 20) {
    return request<ChatConversationsPageResponse>(`/v1/chat/conversations?page=${page}&limit=${limit}`, { token });
  },
  chatMessages(token: string, conversationId: string, page = 1, limit = 80) {
    return request<ChatMessagesPageResponse>(`/v1/chat/conversations/${encodeURIComponent(conversationId)}/messages?page=${page}&limit=${limit}`, { token });
  },
  memoryCards(token: string, section = "people", q = "", limit = 24) {
    return request<MemoryCardsResponse>(`/v1/memory/cards?section=${encodeURIComponent(section)}&q=${encodeURIComponent(q)}&limit=${limit}`, { token });
  },
  memoryCard(token: string, entityId: string) {
    return request<MemoryCardDetailResponse>(`/v1/memory/cards/${encodeURIComponent(entityId)}`, { token });
  },
  status(token: string) {
    return request<StatsResponse>("/v1/status", { token });
  },
  deepHealth(token: string) {
    return request<DeepHealthResponse>("/v1/health/deep", { token });
  },
  ingest(token: string, text: string, userImportance: number | null = null, idempotencyKey?: string) {
    const messageId = idempotencyKey || crypto.randomUUID();
    return request<IngestResponse>("/v1/entries", {
      method: "POST",
      token,
      body: { text, user_importance: userImportance, message_id: messageId },
      idempotencyKey: messageId,
    });
  },
  ask(token: string, query: string) {
    return request<AskResponse>(`/v1/ask?q=${encodeURIComponent(query)}`, { token });
  },
  report(token: string, type: "daily" | "weekly" | "monthly", query = "") {
    return request<ReportResponse>(`/v1/reports?type=${encodeURIComponent(type)}&query=${encodeURIComponent(query)}`, { token });
  },
  entries(token: string, page = 1, limit = 20) {
    return request<EntriesPageResponse>(`/v1/entries?page=${page}&limit=${limit}`, { token });
  },
  updateEntryImportance(token: string, entryId: string, userImportance: number | null) {
    return request<EntryResponse>(`/v1/entries/${encodeURIComponent(entryId)}/importance`, {
      method: "PATCH",
      token,
      body: { user_importance: userImportance },
    });
  },
  deleteEntry(token: string, entryId: string) {
    return request<{ status: string; entry_id: string }>(`/v1/entries/${entryId}`, {
      method: "DELETE",
      token,
    });
  },
  createLibrarySource(token: string, body: LibraryIngestRequest) {
    return request<LibraryIngestResponse>("/v1/library", {
      method: "POST",
      token,
      body,
    });
  },
  async uploadFile(token: string, file: File, options: {
    destination?: UploadDestination;
    caption?: string | null;
    title?: string | null;
    source_type?: string | null;
    conversation_id?: string;
  } = {}) {
    return request<UploadIngestResponse>("/v1/uploads", {
      method: "POST",
      token,
      body: {
        filename: file.name || "upload",
        media_type: file.type || null,
        content_base64: await blobToBase64(file),
        destination: options.destination || "auto",
        caption: options.caption || null,
        title: options.title || null,
        source_type: options.source_type || null,
        surface: "web",
        conversation_id: options.conversation_id || "uploads",
      },
    });
  },
  async importObsidianVault(token: string, file: File, mode: VaultImportMode = "auto", dryRun = false) {
    return request<VaultImportResponse>("/v1/import/obsidian", {
      method: "POST",
      token,
      body: {
        filename: file.name || "obsidian-vault.zip",
        content_base64: await blobToBase64(file),
        mode,
        dry_run: dryRun,
      },
    });
  },
  createVaultImportUpload(
    token: string,
    file: File,
    mode: VaultImportMode = "auto",
    conflictPolicy: VaultConflictPolicy = "skip",
    signal?: AbortSignal,
  ) {
    return request<VaultImportSessionResponse>("/v1/import/obsidian/uploads", {
      method: "POST",
      token,
      signal,
      body: {
        filename: file.name || "obsidian-vault.zip",
        expected_bytes: file.size,
        mode,
        conflict_policy: conflictPolicy,
      },
    });
  },
  async appendVaultImportChunk(
    token: string,
    transferId: string,
    offset: number,
    chunk: Blob,
    signal?: AbortSignal,
  ) {
    const chunkSha256 = await sha256Hex(chunk);
    return request<VaultImportSessionResponse>(`/v1/import/obsidian/uploads/${encodeURIComponent(transferId)}/chunks`, {
      method: "PUT",
      token,
      signal,
      idempotencyKey: `vault-chunk-${transferId}-${offset}-${chunkSha256.slice(0, 16)}`,
      body: {
        offset,
        content_base64: await blobToBase64(chunk),
        chunk_sha256: chunkSha256,
      },
    });
  },
  vaultImportSession(token: string, transferId: string, signal?: AbortSignal) {
    return request<VaultImportSessionResponse>(`/v1/import/obsidian/uploads/${encodeURIComponent(transferId)}`, {
      token,
      signal,
    });
  },
  previewVaultImport(token: string, transferId: string, conflictPolicy: VaultConflictPolicy, signal?: AbortSignal) {
    return request<VaultImportSessionResponse>(`/v1/import/obsidian/uploads/${encodeURIComponent(transferId)}/preview`, {
      method: "POST",
      token,
      signal,
      body: { conflict_policy: conflictPolicy },
    });
  },
  applyVaultImport(token: string, transferId: string, conflictPolicy: VaultConflictPolicy, signal?: AbortSignal) {
    return request<VaultImportSessionResponse>(`/v1/import/obsidian/uploads/${encodeURIComponent(transferId)}/apply`, {
      method: "POST",
      token,
      signal,
      body: { conflict_policy: conflictPolicy },
    });
  },
  cancelVaultImport(token: string, transferId: string) {
    return request<VaultImportSessionResponse>(`/v1/import/obsidian/uploads/${encodeURIComponent(transferId)}/cancel`, {
      method: "POST",
      token,
      body: {},
    });
  },
  downloadObsidianVault(token: string) {
    return requestBlob("/v1/export/vault/download?obsidian_defaults=true", { token });
  },
  librarySources(token: string, limit = 50) {
    return request<LibrarySourceResponse[]>(`/v1/library?limit=${limit}`, { token });
  },
  librarySource(token: string, sourceRef: string) {
    return request<LibrarySourceResponse>(`/v1/library/${encodeURIComponent(sourceRef)}`, { token });
  },
  preferences(token: string) {
    return request<PreferencesResponse>("/v1/preferences", { token });
  },
  updatePreferences(token: string, body: PreferencesUpdateRequest) {
    return request<PreferencesResponse>("/v1/preferences", {
      method: "PATCH",
      token,
      body,
    });
  },
  voiceArchive(token: string) {
    return request<VoiceArchiveStatusResponse>("/v1/voice-archive", { token });
  },
  enableVoiceArchive(token: string, body: VoiceArchiveConsentRequest) {
    return request<VoiceArchiveStatusResponse>("/v1/voice-archive/consent", {
      method: "POST",
      token,
      body,
    });
  },
  disableVoiceArchive(token: string) {
    return request<VoiceArchiveStatusResponse>("/v1/voice-archive/consent", {
      method: "DELETE",
      token,
    });
  },
  deleteVoiceArchive(token: string) {
    return request<VoiceArchiveDeleteResponse>("/v1/voice-archive", {
      method: "DELETE",
      token,
      body: { confirm: "DELETE VOICE ARCHIVE" },
    });
  },
  acceptLegalDocument(token: string, document: LegalDocument, version: string) {
    return request<PreferencesResponse>("/v1/legal/acceptances", {
      method: "POST",
      token,
      body: { document, version },
    });
  },
  createSafetyReport(token: string, body: SafetyReportRequest) {
    return request<SafetyReportResponse>("/v1/safety/reports", {
      method: "POST",
      token,
      body: { source: "web", target_type: "general", ...body },
    });
  },
  devices(token: string) {
    return request<DevicesPageResponse>("/v1/devices", { token });
  },
  registerDevice(token: string, body: DeviceRegistrationRequest) {
    return request<DeviceResponse>("/v1/devices", {
      method: "POST",
      token,
      body,
    });
  },
  revokeDevice(token: string, installationId: string) {
    return request<DeviceResponse>(`/v1/devices/${encodeURIComponent(installationId)}`, {
      method: "DELETE",
      token,
    });
  },
  sessions(token: string) {
    return request<SessionsPageResponse>("/v1/sessions", { token });
  },
  revokeSession(token: string, sessionId: string) {
    return request<SessionResponse>(`/v1/sessions/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
      token,
    });
  },
  revokeOtherSessions(token: string) {
    return request<{ status: string; count: number }>("/v1/sessions/revoke-others", {
      method: "POST",
      token,
    });
  },
  jobs(token: string, status = "", page = 1, limit = 20) {
    const suffix = status ? `&status=${encodeURIComponent(status)}` : "";
    return request<JobsPageResponse>(`/v1/jobs?page=${page}&limit=${limit}${suffix}`, { token });
  },
  job(token: string, jobId: string) {
    return request<JobResponse>(`/v1/jobs/${jobId}`, { token });
  },
  retryJob(token: string, jobId: string) {
    return request<JobResponse>(`/v1/jobs/${jobId}/retry`, { method: "POST", token });
  },
  cancelJob(token: string, jobId: string) {
    return request<JobResponse>(`/v1/jobs/${jobId}/cancel`, { method: "POST", token });
  },
  exportAccount(token: string) {
    return request<AccountExportResponse>("/v1/export", { token });
  },
  deleteAccount(token: string) {
    return request<{ status: string; deleted: Record<string, number> }>("/v1/me", {
      method: "DELETE",
      token,
      body: { confirm: "DELETE" },
    });
  },
};
