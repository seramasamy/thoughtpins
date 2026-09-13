import type { Page, Route } from "@playwright/test";

export type MockMode = "local" | "maintenance" | "auth" | "offline";

const now = "2026-07-01T06:00:00Z";

export async function installMockApi(
  page: Page,
  mode: MockMode = "local",
  chatDelayMs = 0,
  fixture: "review" | "product" = "review",
  options: {
    voiceArchiveEnabled?: boolean;
    inviteRequired?: boolean;
    inviteAdmitted?: boolean;
    aiConsentAccepted?: boolean;
    magicLinkEnabled?: boolean;
    appleClientId?: string;
  } = {},
) {
  if (mode === "offline") {
    await page.route("**/v1/client-config", async (route) => route.abort("failed"));
    return;
  }

  // Authentication fixtures never need to contact Apple's live CDN. Provider
  // workflow tests install their own later route with explicit SDK behavior.
  await page.route("https://appleid.cdn-apple.com/**", route => route.fulfill({
    contentType: "application/javascript", body: "/* fictional provider fixture */",
  }));

  let inviteAdmitted = Boolean(options.inviteAdmitted);
  let chatPostCount = 0;
  let libraryPostCount = 0;
  let uploadPostCount = 0;
  let vaultImportCount = 0;
  let vaultExpectedBytes = 0;
  let vaultReceivedBytes = 0;
  let vaultTransferStatus = "uploading";
  let exportCount = 0;
  let deleteAccountCount = 0;
  let preferencesPatchCount = 0;
  let responseStyle = "friendly";
  let importancePromptsEnabled = false;
  let lastChatPayload: Record<string, unknown> | null = null;
  let voiceArchiveStatus = voiceArchive(false);
  const legalAcceptances: Record<string, { version: string; accepted_at_utc: string }> = options.aiConsentAccepted
    ? { ai_disclosure: { version: "2026-07-13", accepted_at_utc: now } }
    : {};
  const chatMessages: Array<Record<string, unknown>> = [];

  await page.route("**/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    if (path === "/v1/client-config") {
      return json(route, {
        ...clientConfig(mode, Boolean(options.voiceArchiveEnabled)),
        invite_required: Boolean(options.inviteRequired),
        invite_request_email: "invite@thoughtpins.com",
        magic_link_enabled: Boolean(options.magicLinkEnabled),
        oauth_apple_client_id: options.appleClientId ?? "com.thoughtpins.web.fixture",
      });
    }
    if (path === "/v1/invites/request" && method === "POST") {
      return json(route, { status: "received", note: (request.postDataJSON() as { note?: string } | null)?.note || null, requested_at_utc: now });
    }
    if (path === "/v1/invites/status") {
      return json(route, inviteStatus(Boolean(options.inviteRequired), inviteAdmitted));
    }
    if (path === "/v1/invites/redeem" && method === "POST") {
      const submitted = String((request.postDataJSON() as { code?: string } | null)?.code || "")
        .toUpperCase()
        .replace(/[^A-Z0-9]/g, "");
      if (submitted === "ABCDEFGHJKLM") {
        inviteAdmitted = true;
        return json(route, inviteStatus(true, true));
      }
      return json(route, { error: { code: "invite_required", message: "That code is not valid.", request_id: "req" } }, 403);
    }
    if (path === "/v1/auth/login" && method === "POST") {
      return json(route, { access_token: "test-access", refresh_token: "test-refresh", token_type: "bearer", expires_in: 3600 });
    }
    if (path === "/v1/auth/register" && method === "POST") {
      return json(route, { status: "created", user_id: "review-user", api_key: null });
    }
    if (path === "/v1/auth/logout" && method === "POST") {
      return json(route, { status: "ok" });
    }
    if (path === "/v1/me" && method === "GET") {
      return json(route, me(fixture));
    }
    if (path === "/v1/me" && method === "DELETE") {
      deleteAccountCount += 1;
      return json(route, { status: "deleted", deleted: { raw_entries: 1, memories: 3 } });
    }
    if (path === "/v1/voice-archive" && method === "GET") {
      return json(route, voiceArchiveStatus);
    }
    if (path === "/v1/voice-archive/consent" && method === "POST") {
      voiceArchiveStatus = voiceArchive(true);
      return json(route, voiceArchiveStatus);
    }
    if (path === "/v1/voice-archive/consent" && method === "DELETE") {
      voiceArchiveStatus = voiceArchive(false);
      return json(route, voiceArchiveStatus);
    }
    if (path === "/v1/voice-archive" && method === "DELETE") {
      voiceArchiveStatus = voiceArchive(false);
      return json(route, { status: "deleted", deleted: { voice_assets: 0, original_bytes: 0, stored_bytes: 0 } });
    }
    if (path === "/v1/chat/conversations") {
      const items = chatMessages.length ? [{
        id: "review-conversation",
        conversation_key: "web:main",
        surface: "web",
        title: "main",
        created_at_utc: now,
        updated_at_utc: now,
        last_message_at_utc: now,
      }] : [];
      return json(route, { items, page: 1, limit: 50, total: items.length, has_next: false });
    }
    if (path === "/v1/chat/conversations/review-conversation/messages") {
      return json(route, { items: chatMessages, page: 1, limit: 100, total: chatMessages.length, has_next: false });
    }
    if (path === "/v1/chat" && method === "POST") {
      chatPostCount += 1;
      const payload = request.postDataJSON() as { text?: string; include_private?: boolean };
      lastChatPayload = payload;
      if (chatDelayMs > 0) await new Promise((resolve) => setTimeout(resolve, chatDelayMs));
      chatMessages.push(
        {
          id: `chat-user-${chatPostCount}`,
          conversation_id: "review-conversation",
          role: "user",
          text: payload.text || "",
          route_type: "chat",
          status: "sent",
          entry_id: null,
          job_id: null,
          document_id: null,
          created_at_utc: now,
          metadata: {},
        },
        {
          id: `chat-assistant-${chatPostCount}`,
          conversation_id: "review-conversation",
          role: "assistant",
          text: "I remember the Atlas Cafe note and the copper lantern detail.",
          route_type: "chat",
          status: "replied",
          entry_id: null,
          job_id: null,
          document_id: null,
          created_at_utc: now,
          metadata: {},
        },
      );
      return json(route, {
        status: "completed",
        route_type: "chat",
        reply: "I remember the Atlas Cafe note and the copper lantern detail.",
        entry_id: null,
        job_id: null,
        document_id: null,
        requires_confirmation: false,
        confirmation_prompt: null,
        context_size_chars: 1842,
        metadata: { routing_hint: "Replying as chat." },
      });
    }
    if (path === "/v1/memory/cards") {
      return json(route, memoryCards());
    }
    if (path.startsWith("/v1/memory/cards/")) {
      return json(route, memoryCards().items[0]);
    }
    if (path === "/v1/library" && method === "GET") {
      return json(route, [librarySource()]);
    }
    if (path === "/v1/library" && method === "POST") {
      libraryPostCount += 1;
      return json(route, {
        document_id: "doc_1",
        raw_entry_id: "entry_doc_1",
        title: "Review Article",
        source_type: "article",
        status: "processed",
        chunks: 2,
        memories: 4,
        source_url: "https://example.com/review",
        duplicate: false,
        error: null,
        access_method: "local",
        rights_basis: "user_provided",
        paywall_detected: false,
      });
    }
    if (path.startsWith("/v1/library/")) {
      return json(route, librarySource());
    }
    if (path === "/v1/uploads" && method === "POST") {
      uploadPostCount += 1;
      return json(route, {
        status: "processed",
        route_type: "library",
        filename: "review.txt",
        media_kind: "text",
        destination: "library",
        extraction_status: "ok",
        extracted_chars: 48,
        attachment_saved: true,
        attachment_ref: "attachments/review.txt",
        title: "review.txt",
        entry_id: null,
        job_id: null,
        document_id: "doc_upload_1",
        error: null,
        metadata: {},
      });
    }
    if (path === "/v1/import/obsidian/uploads" && method === "POST") {
      const payload = request.postDataJSON() as { expected_bytes?: number };
      vaultImportCount += 1;
      vaultExpectedBytes = payload.expected_bytes || 0;
      vaultReceivedBytes = 0;
      vaultTransferStatus = "uploading";
      return json(route, vaultTransferSession(vaultTransferStatus, vaultExpectedBytes, vaultReceivedBytes));
    }
    if (path === "/v1/import/obsidian/uploads/transfer-1/chunks" && method === "PUT") {
      const payload = request.postDataJSON() as { offset?: number; content_base64?: string };
      const chunkBytes = Buffer.from(payload.content_base64 || "", "base64").length;
      vaultReceivedBytes = (payload.offset || 0) + chunkBytes;
      vaultTransferStatus = vaultReceivedBytes >= vaultExpectedBytes ? "uploaded" : "uploading";
      return json(route, vaultTransferSession(vaultTransferStatus, vaultExpectedBytes, vaultReceivedBytes));
    }
    if (path === "/v1/import/obsidian/uploads/transfer-1/preview" && method === "POST") {
      vaultTransferStatus = "preview_ready";
      return json(route, vaultTransferSession(vaultTransferStatus, vaultExpectedBytes, vaultReceivedBytes));
    }
    if (path === "/v1/import/obsidian/uploads/transfer-1/apply" && method === "POST") {
      vaultTransferStatus = "completed";
      return json(route, vaultTransferSession(vaultTransferStatus, vaultExpectedBytes, vaultReceivedBytes));
    }
    if (path === "/v1/import/obsidian/uploads/transfer-1/cancel" && method === "POST") {
      vaultTransferStatus = "canceled";
      return json(route, vaultTransferSession(vaultTransferStatus, vaultExpectedBytes, vaultReceivedBytes));
    }
    if (path === "/v1/import/obsidian/uploads/transfer-1" && method === "GET") {
      return json(route, vaultTransferSession(vaultTransferStatus, vaultExpectedBytes, vaultReceivedBytes));
    }
    if (path === "/v1/import/obsidian" && method === "POST") {
      vaultImportCount += 1;
      return json(route, vaultImportResult("completed"));
    }
    if (path === "/v1/entries" && method === "GET") {
      return json(route, {
        items: [{ id: "entry_1", created_at_utc: now, local_date: "2026-07-10", local_time: "02:00", source: "web", raw_text: "Met Maya at Atlas Cafe.", sensitivity: "normal", processed_status: "completed", processing_error: null, user_importance: 4, importance_source: "user", importance_updated_at: now }],
        page: 1,
        limit: 20,
        total: 1,
        has_next: false,
      });
    }
    if (path === "/v1/entries/entry_1/importance" && method === "PATCH") {
      const payload = request.postDataJSON() as { user_importance: number | null };
      return json(route, { id: "entry_1", created_at_utc: now, local_date: "2026-07-10", local_time: "02:00", source: "web", raw_text: "Met Maya at Atlas Cafe.", sensitivity: "normal", processed_status: "completed", processing_error: null, user_importance: payload.user_importance, importance_source: "api", importance_updated_at: now });
    }
    if (path === "/v1/reports") {
      const period = new URL(request.url()).searchParams.get("type") || "daily";
      return json(route, {
        report_type: period,
        query: "",
        markdown: `# ${period === "daily" ? "Daily Recap" : period === "weekly" ? "Weekly Report" : "Monthly Report"}: 2026-07-10 to 2026-07-10\n\n**Entries:** 1\n**Events:** 1\n**Memories extracted:** 3\n\n## Events\n- **2026-07-10** - Met Maya at Atlas Cafe\n\n## People Mentioned\n- [[Maya]]\n\n## Notable Memories\n- Copper lantern detail at Atlas Cafe`,
        path: `reports/${period}.md`,
        user_id: "review-user",
      });
    }
    if (path === "/v1/entries" && method === "POST") {
      return json(route, { status: "completed", entry_id: "entry_new", job_id: null, entities: 2, events: 1, memories: 3, relationships: 1 });
    }
    if (path === "/v1/status") {
      return json(route, { raw_entries: 1, entities: 4, memories: 8, relationships: 3, events: 1, action_items: 0, expenses: 0, sources: 1, uptime_seconds: 120, vault_files: 12 });
    }
    if (path === "/v1/health/deep") {
      return json(route, {
        status: "ok",
        uptime_seconds: 120,
        version: "1.0.0-rc.1",
        checks: {
          db: { status: "ok" },
          redis: { status: "ok" },
          llm: { status: "configured", provider: "openai_compatible", model: "configured-chat-model" },
          vector: { status: "configured", embedding_provider: "openai" },
          jobs: { status: "ok", pending: 0, retry: 0, queued: 0, running: 0, failed: 0, dead_letter: 0 },
          worker: { status: "ok" },
        },
      });
    }
    if (path === "/v1/jobs") {
      return json(route, { items: [], page: 1, limit: 20, total: 0, has_next: false });
    }
    if (path === "/v1/preferences" && method === "PATCH") {
      const payload = request.postDataJSON() as { response_style?: string; importance_prompts_enabled?: boolean };
      if (["friendly", "clear", "mirror"].includes(payload.response_style || "")) {
        responseStyle = payload.response_style!;
      }
      if (typeof payload.importance_prompts_enabled === "boolean") {
        importancePromptsEnabled = payload.importance_prompts_enabled;
      }
      preferencesPatchCount += 1;
      return json(route, preferences(responseStyle, importancePromptsEnabled, legalAcceptances));
    }
    if (path === "/v1/preferences") {
      return json(route, preferences(responseStyle, importancePromptsEnabled, legalAcceptances));
    }
    if (path === "/v1/legal/acceptances" && method === "POST") {
      const payload = request.postDataJSON() as { document?: string; version?: string };
      if (payload.document && payload.version) {
        legalAcceptances[payload.document] = { version: payload.version, accepted_at_utc: now };
      }
      return json(route, preferences(responseStyle, importancePromptsEnabled, legalAcceptances));
    }
    if (path === "/v1/devices") {
      return json(route, { items: [], total: 0 });
    }
    if (path === "/v1/sessions" && method === "GET") {
      return json(route, {
        items: [
          {
            id: "session-review-current",
            current: true,
            created_at_utc: now,
            expires_at_utc: "2026-07-31T06:00:00Z",
            revoked_at_utc: null,
            user_agent: "Thought Pins review browser",
            ip_address: null,
          },
        ],
        total: 1,
      });
    }
    if (path === "/v1/sessions/revoke-others" && method === "POST") {
      return json(route, { status: "ok", count: 0 });
    }
    if (path.startsWith("/v1/sessions/") && method === "DELETE") {
      return json(route, {
        id: path.slice("/v1/sessions/".length),
        current: false,
        created_at_utc: now,
        expires_at_utc: "2026-07-31T06:00:00Z",
        revoked_at_utc: now,
        user_agent: "Thought Pins review browser",
        ip_address: null,
      });
    }
    if (path === "/v1/export") {
      exportCount += 1;
      return json(route, { exported_at_utc: now, user: { id: "review-user" }, tables: { raw_entries: [] } });
    }

    return json(route, {}, 404);
  });

  return {
    getChatPostCount: () => chatPostCount,
    getLibraryPostCount: () => libraryPostCount,
    getUploadPostCount: () => uploadPostCount,
    getVaultImportCount: () => vaultImportCount,
    getExportCount: () => exportCount,
    getDeleteAccountCount: () => deleteAccountCount,
    getPreferencesPatchCount: () => preferencesPatchCount,
    getResponseStyle: () => responseStyle,
    getImportancePromptsEnabled: () => importancePromptsEnabled,
    getLastChatPayload: () => lastChatPayload,
  };
}

function vaultTransferSession(status: string, expectedBytes: number, receivedBytes: number) {
  const hasResult = status === "preview_ready" || status === "completed";
  const progress = expectedBytes > 0 ? Math.min(100, receivedBytes / expectedBytes * 100) : 0;
  return {
    id: "transfer-1",
    status,
    operation: status === "preview_ready" ? "preview" : status === "completed" ? "apply" : null,
    filename: "review-vault.zip",
    mode: "auto",
    conflict_policy: "skip",
    expected_bytes: expectedBytes,
    received_bytes: receivedBytes,
    archive_sha256: receivedBytes >= expectedBytes ? "review-archive-hash" : null,
    progress_current: receivedBytes,
    progress_total: expectedBytes,
    progress_percent: status === "completed" || status === "preview_ready" ? 100 : progress,
    progress_stage: status,
    cancel_requested: status === "canceled",
    result: hasResult ? vaultImportResult(status) : null,
    error: null,
    created_at_utc: now,
    updated_at_utc: now,
    finished_at_utc: status === "completed" || status === "canceled" ? now : null,
    expires_at_utc: "2026-07-02T06:00:00Z",
  };
}

function vaultImportResult(status: string) {
  return {
    status,
    format: "obsidian_vault",
    mode: "auto",
    thoughtpins_export: false,
    dry_run: status !== "completed",
    archive_sha256: "review-archive-hash",
    files_discovered: 3,
    notes_discovered: 2,
    attachments_skipped: 1,
    structural_files_skipped: 1,
    canvases_discovered: 1,
    canvas_documents_imported: 1,
    journal_notes: 1,
    library_notes: 1,
    journal_jobs_queued: status === "completed" ? 1 : 0,
    library_documents_imported: status === "completed" ? 1 : 0,
    new_notes: 2,
    changed_notes: 0,
    unchanged_notes: 0,
    conflicts: 0,
    duplicates: 0,
    skipped: 0,
    imported: status === "completed" ? 2 : 0,
    warnings: [],
    errors: [],
    job_ids: status === "completed" ? ["job_vault_1"] : [],
    document_ids: status === "completed" ? ["doc_vault_1"] : [],
    preview_items: [
      { path: "Journal/2026-07-01.md", title: "July 1", kind: "journal", state: "new", action: "import" },
      { path: "Notes/Reading.md", title: "Reading", kind: "library", state: "new", action: "import" },
    ],
  };
}

function clientConfig(mode: MockMode, voiceArchiveEnabled = false) {
  return {
    app_name: "Thought Pins",
    api_version: "1.0.0-rc.1",
    environment: "staging",
    auth_required: mode === "auth",
    registration_locked: mode !== "auth" ? false : false,

    oauth_google_enabled: true,
    oauth_apple_enabled: true,
    ai_processing: "configured",
    memory_context_mode: "smart",
    voice_archive_enabled: voiceArchiveEnabled,
    privacy_policy_url: "https://thoughtpins.com/privacy",
    terms_url: "https://thoughtpins.com/terms",
    support_url: "https://thoughtpins.com/support",
    account_deletion_url: "https://thoughtpins.com/account/delete",
    ai_disclosure_url: "https://thoughtpins.com/ai-disclosure",
    legal_document_version: "2026-07-13",
    minimum_supported_clients: { ios: "1.0.0", android: "1.0.0", web: "1.0.0" },
    recommended_clients: { ios: "1.0.0", android: "1.0.0", web: "1.0.0" },
    store_urls: { ios: null, android: null, web: "https://thoughtpins.com/app" },
    maintenance_mode: mode === "maintenance",
    maintenance_message: mode === "maintenance" ? "Thought Pins is in maintenance for a short upgrade. Please try again soon." : null,
    maintenance_retry_after_seconds: mode === "maintenance" ? 300 : null,
    maintenance_allow_reads: true,
  };
}

function voiceArchive(enabled: boolean) {
  return {
    enabled,
    consent_version: enabled ? "2026-07-13" : null,
    current_consent_version: "2026-07-13",
    consented_at_utc: enabled ? now : null,
    asset_count: 0,
    original_bytes: 0,
    stored_bytes: 0,
    default_processing: "ephemeral",
    retention_purpose: "personal_voice_features",
    derived_voice_data_created: false,
  };
}

function me(fixture: "review" | "product") {
  return {
    id: fixture === "product" ? "product-user" : "review-user",
    email: fixture === "product" ? "avery@example.com" : "review@example.com",
    phone: null,
    display_name: fixture === "product" ? "Avery Chen" : "Review User",
    is_admin: false,
    auth_method: "password",
    created_at_utc: now,
    last_login_utc: now,
  };
}

function preferences(responseStyle = "friendly", importancePromptsEnabled = false, legalAcceptances: Record<string, { version: string; accepted_at_utc: string }> = {}) {
  return { notifications_enabled: false, reminder_hour_local: null, timezone: "America/New_York", private_entries_in_ask: false, weekly_digest_enabled: false, product_updates_enabled: false, preferred_name: "Review", response_style: responseStyle, importance_prompts_enabled: importancePromptsEnabled, legal_acceptances: legalAcceptances, updated_at_utc: now };
}

function memoryCards() {
  return {
    section: "people",
    query: "",
    sections: { people: ["person"], places: ["place"], concepts: ["concept"], events: ["event"], projects: ["project"], organizations: ["organization"], things: ["thing"] },
    items: [{
      id: "entity_maya",
      name: "Maya",
      type: "person",
      subtitle: "TP_DEMO_CORPUS: Atlas Cafe, copper lantern detail",
      aliases: [],
      attributes: [],
      memory_count: 3,
      mention_count: 2,
      relationship_count: 1,
      salience_score: 0.81,
      salience_uncertainty: 0.2,
      salience_tier: "central",
      salience_model_version: "salience-v2",
      first_seen_at_utc: now,
      last_seen: "2026-07-01",
      statline: { memories: 3, mentions: 2 },
      recent_memories: [{ id: "mem_1", entry_id: "entry_1", date: "2026-07-01", type: "note", text: "Maya noticed the copper lantern detail at Atlas Cafe.", confidence: "high" }],
      all_memories: [{ id: "mem_1", entry_id: "entry_1", date: "2026-07-01", type: "note", text: "[TP_DEMO_CORPUS] Maya noticed the copper lantern detail at Atlas Cafe.", confidence: "high" }],
      relationships: [{ type: "met_at", other: "Atlas Cafe", confidence: "high", evidence_count: 1 }],
      source_documents: [{ id: "doc_1", title: "Review Article", source_type: "article", status: "processed", source_url: "https://example.com/review", obsidian_path: "Library/Articles/Review Article.md" }],
      timeline: [{ date: "2026-07-01", label: "Mentioned at Atlas Cafe", source: "entry_1" }],
      provenance: { source_entries: 1, salience: { score: 0.81, uncertainty: 0.2, tier: "central", model_version: "salience-v2" } },
      ask_prompt: "What should I remember about Maya?",
      obsidian_path: "People/Maya.md",
    }],
    total: 1,
  };
}

function librarySource() {
  return {
    id: "doc_1",
    title: "Review Article",
    source_type: "article",
    status: "processed",
    source_url: "https://example.com/review?utm_source=share",
    original_url: "https://example.com/review",
    canonical_url: "https://example.com/review",
    source_domain: "example.com",
    author: "Example",
    published_at: "2026-07-01T12:00:00",
    publisher: "Example Review",
    topics: ["technology", "culture"],
    key_concepts: ["Durable Recall", "Source Context"],
    access_method: "local",
    rights_basis: "user_provided",
    fetch_status: "ok",
    paywall_detected: false,
    retrieval_quality_score: 0.98,
    summary: "[TP_DEMO_CORPUS] A review article about recall quality.",
    created_at_utc: now,
    chunks: 2,
  };
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function inviteStatus(required: boolean, admitted: boolean) {
  return {
    invite_required: required,
    invite_redeemed: admitted,
    admitted: !required || admitted,
    contact_email: "invite@thoughtpins.com",
    attempts_remaining: 10,
  };
}
