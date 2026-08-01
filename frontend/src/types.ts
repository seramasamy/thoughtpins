export type TokenResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
};

export type ClientConfigResponse = {
  app_name: string;
  api_version: string;
  environment: string;
  auth_required: boolean;
  registration_locked: boolean;

  oauth_google_enabled: boolean;
  oauth_apple_enabled: boolean;
  oauth_google_client_id?: string | null;
  oauth_apple_client_id?: string | null;
  magic_link_enabled?: boolean;
  voice_archive_enabled: boolean;
  ai_processing: string;
  memory_context_mode: string;
  privacy_policy_url: string | null;
  terms_url: string | null;
  support_url: string | null;
  account_deletion_url: string | null;
  ai_disclosure_url: string | null;
  legal_document_version: string;
  minimum_supported_clients: Record<"ios" | "android" | "web", string>;
  recommended_clients: Record<"ios" | "android" | "web", string>;
  store_urls: Record<"ios" | "android" | "web", string | null>;
  maintenance_mode: boolean;
  maintenance_message: string | null;
  maintenance_retry_after_seconds: number | null;
  maintenance_allow_reads: boolean;
};

export type PreferencesResponse = {
  notifications_enabled: boolean;
  reminder_hour_local: number | null;
  timezone: string | null;
  private_entries_in_ask: boolean;
  weekly_digest_enabled: boolean;
  product_updates_enabled: boolean;
  preferred_name: string | null;
  response_style: "friendly" | "clear" | "mirror";
  importance_prompts_enabled: boolean;
  legal_acceptances: Record<string, { version: string; accepted_at_utc: string }>;
  updated_at_utc: string | null;
};

export type PreferencesUpdateRequest = Partial<{
  notifications_enabled: boolean;
  reminder_hour_local: number | null;
  timezone: string | null;
  private_entries_in_ask: boolean;
  weekly_digest_enabled: boolean;
  product_updates_enabled: boolean;
  preferred_name: string | null;
  response_style: "friendly" | "clear" | "mirror";
  importance_prompts_enabled: boolean;
}>;

export type LegalDocument = "privacy" | "terms" | "ai_disclosure";

export type VoiceArchiveStatusResponse = {
  enabled: boolean;
  consent_version: string | null;
  current_consent_version: string;
  consented_at_utc: string | null;
  asset_count: number;
  original_bytes: number;
  stored_bytes: number;
  default_processing: "ephemeral";
  retention_purpose: "personal_voice_features";
  derived_voice_data_created: boolean;
};

export type VoiceArchiveConsentRequest = {
  retain_recordings: boolean;
  acknowledge_sensitive_audio: boolean;
  acknowledge_personal_use_only: boolean;
  acknowledge_deletion_available: boolean;
};

export type VoiceArchiveDeleteResponse = {
  status: string;
  deleted: Record<string, number>;
};

export type SafetyReportCategory =
  | "unsafe_ai_output"
  | "harmful_or_illegal_content"
  | "copyright_concern"
  | "privacy_concern"
  | "harassment_or_abuse"
  | "self_harm_or_crisis"
  | "security_concern"
  | "other";

export type SafetyReportRequest = {
  category: SafetyReportCategory;
  summary: string;
  target_type?: "general" | "chat_message" | "document_source" | "raw_entry" | "memory_card" | "account" | null;
  target_id?: string | null;
  source?: "web" | "ios" | "android" | "telegram" | "api";
  metadata?: Record<string, unknown>;
};

export type SafetyReportResponse = {
  id: string;
  status: string;
  category: SafetyReportCategory;
  created_at_utc: string | null;
  support_channel: string;
};

export type DeviceRegistrationRequest = {
  installation_id: string;
  platform: "ios" | "android" | "web";
  device_name?: string | null;
  app_version?: string | null;
  build_number?: string | null;
  os_version?: string | null;
  locale?: string | null;
  timezone?: string | null;
  push_provider?: "apns" | "fcm" | "webpush" | null;
  push_token?: string | null;
  notifications_enabled?: boolean;
  metadata?: Record<string, unknown>;
};

export type DeviceResponse = Omit<DeviceRegistrationRequest, "push_token" | "metadata"> & {
  id: string;
  push_token_present: boolean;
  notifications_enabled: boolean;
  created_at_utc: string | null;
  last_seen_at_utc: string | null;
  revoked_at_utc: string | null;
};

export type DevicesPageResponse = {
  items: DeviceResponse[];
  total: number;
};

export type SessionResponse = {
  id: string;
  current: boolean;
  created_at_utc: string | null;
  expires_at_utc: string | null;
  revoked_at_utc: string | null;
  user_agent: string | null;
  ip_address: string | null;
};

export type SessionsPageResponse = {
  items: SessionResponse[];
  total: number;
};

export type SignInMethodsResponse = {
  email: string | null;
  phone: string | null;
  password_set: boolean;
  email_verified: boolean;
  oauth_providers: string[];
  magic_link_available: boolean;
  password_change_requires: "current_password" | "email_code" | "unavailable";
};

export type PasswordSetRequest = {
  new_password: string;
  current_password?: string;
  code?: string;
};

export type PasswordSetResponse = {
  status: string;
  password_set: boolean;
  other_sessions_revoked: number;
};

export type MeResponse = {
  id: string;
  email: string | null;
  phone: string | null;
  display_name: string | null;
  is_admin: boolean;
  auth_method: string;
  created_at_utc: string | null;
  last_login_utc: string | null;
};

export type IngestResponse = {
  status: string;
  entry_id: string;
  job_id: string | null;
  entities: number;
  events: number;
  memories: number;
  relationships: number;
  user_importance: number | null;
};

export type LibraryIngestRequest = {
  text?: string | null;
  url?: string | null;
  title?: string | null;
  author?: string | null;
  source_type?: string;
};

export type LibraryIngestResponse = {
  document_id: string;
  raw_entry_id: string;
  title: string;
  source_type: string;
  status: string;
  chunks: number;
  memories: number;
  source_url: string | null;
  duplicate: boolean;
  error: string | null;
  access_method: string | null;
  rights_basis: string | null;
  paywall_detected: boolean;
};

export type UploadDestination = "auto" | "journal" | "library";

export type UploadIngestRequest = {
  filename: string;
  content_base64: string;
  media_type?: string | null;
  destination?: UploadDestination;
  caption?: string | null;
  title?: string | null;
  source_type?: string | null;
  surface?: string;
  conversation_id?: string;
};

export type UploadIngestResponse = {
  status: string;
  route_type: string;
  filename: string;
  media_kind: string;
  destination: string;
  extraction_status: string;
  extracted_chars: number;
  attachment_saved: boolean;
  attachment_ref: string | null;
  voice_asset_id: string | null;
  title: string | null;
  entry_id: string | null;
  job_id: string | null;
  document_id: string | null;
  error: string | null;
  metadata: Record<string, unknown>;
};

export type VaultImportMode = "auto" | "all_library" | "all_journal";
export type VaultConflictPolicy = "skip" | "append";

export type VaultImportPreviewItem = {
  path: string;
  title: string;
  kind: "journal" | "library";
  state: "new" | "unchanged" | "changed";
  action: "import" | "skip_duplicate" | "skip_conflict" | "append_revision";
};

export type VaultImportResponse = {
  status: string;
  format: string;
  mode: VaultImportMode;
  thoughtpins_export: boolean;
  dry_run: boolean;
  archive_sha256: string;
  files_discovered: number;
  notes_discovered: number;
  attachments_skipped: number;
  structural_files_skipped: number;
  canvases_discovered: number;
  canvas_documents_imported: number;
  journal_notes: number;
  library_notes: number;
  journal_jobs_queued: number;
  library_documents_imported: number;
  new_notes: number;
  changed_notes: number;
  unchanged_notes: number;
  conflicts: number;
  duplicates: number;
  skipped: number;
  imported: number;
  warnings: string[];
  errors: string[];
  job_ids: string[];
  document_ids: string[];
  preview_items: VaultImportPreviewItem[];
};

export type VaultImportSessionResponse = {
  id: string;
  status: "uploading" | "upload_ready" | "queued" | "running" | "preview_ready" | "completed" | "failed" | "canceled" | "expired" | "cancel_requested";
  operation: "preview" | "apply" | null;
  filename: string;
  mode: VaultImportMode;
  conflict_policy: VaultConflictPolicy;
  expected_bytes: number;
  received_bytes: number;
  archive_sha256: string | null;
  progress_current: number;
  progress_total: number;
  progress_percent: number;
  progress_stage: string;
  cancel_requested: boolean;
  result: VaultImportResponse | null;
  error: string | null;
  created_at_utc: string | null;
  updated_at_utc: string | null;
  finished_at_utc: string | null;
  expires_at_utc: string | null;
};

export type LibrarySourceResponse = {
  id: string;
  title: string;
  source_type: string;
  status: string;
  source_url: string | null;
  original_url: string | null;
  canonical_url: string | null;
  source_domain: string | null;
  author: string | null;
  published_at: string | null;
  publisher: string | null;
  topics: string[];
  key_concepts: string[];
  access_method: string | null;
  rights_basis: string | null;
  fetch_status: string | null;
  paywall_detected: boolean;
  retrieval_quality_score: number | null;
  summary: string | null;
  created_at_utc: string | null;
  chunks: number;
};


export type ChatRequest = {
  text: string;
  conversation_id?: string;
  surface?: string;
  message_id?: string;
  include_private?: boolean;
  confirm_action?: boolean;
  pending_action_id?: string | null;
};

export type ChatResponse = {
  status: string;
  route_type: string;
  reply: string;
  entry_id: string | null;
  job_id: string | null;
  document_id: string | null;
  requires_confirmation: boolean;
  confirmation_prompt: string | null;
  context_size_chars: number;
  metadata: Record<string, unknown>;
};

export type ChatConversationResponse = {
  id: string;
  conversation_key: string;
  surface: string;
  title: string | null;
  created_at_utc: string | null;
  updated_at_utc: string | null;
  last_message_at_utc: string | null;
};

export type ChatConversationsPageResponse = {
  items: ChatConversationResponse[];
  page: number;
  limit: number;
  total: number;
  has_next: boolean;
  next_cursor: string | null;
};

export type ChatMessageResponse = {
  id: string;
  conversation_id: string;
  role: string;
  text: string;
  route_type: string | null;
  status: string | null;
  entry_id: string | null;
  job_id: string | null;
  document_id: string | null;
  created_at_utc: string | null;
  metadata: Record<string, unknown>;
};

export type ChatMessagesPageResponse = {
  items: ChatMessageResponse[];
  page: number;
  limit: number;
  total: number;
  has_next: boolean;
  next_cursor: string | null;
};

export type MemoryCardMemoryResponse = {
  id: string | null;
  entry_id: string | null;
  date: string | null;
  type: string;
  text: string;
  confidence: string | null;
};

export type MemoryCardRelationshipResponse = {
  type: string;
  other: string;
  confidence: string | null;
  evidence_count: number;
};

export type MemoryCardSourceResponse = {
  id: string;
  title: string;
  source_type: string;
  status: string;
  source_url: string | null;
  obsidian_path: string | null;
};

export type MemoryCardTimelineResponse = {
  date: string | null;
  label: string;
  source: string | null;
};
export type MemoryCardResponse = {
  id: string;
  name: string;
  type: string;
  subtitle: string | null;
  aliases: string[];
  attributes: unknown[];
  memory_count: number;
  mention_count: number;
  relationship_count: number;
  salience_score: number;
  salience_uncertainty: number;
  salience_tier: "central" | "notable" | "supporting" | "background";
  salience_model_version: string | null;
  first_seen_at_utc: string | null;
  last_seen: string | null;
  statline: Record<string, unknown>;
  recent_memories: MemoryCardMemoryResponse[];
  relationships: MemoryCardRelationshipResponse[];
  source_documents: MemoryCardSourceResponse[];
  timeline: MemoryCardTimelineResponse[];
  provenance: Record<string, unknown>;
  ask_prompt: string | null;
  obsidian_path: string | null;
};

export type MemoryCardsResponse = {
  section: string;
  query: string;
  sections: Record<string, string[]>;
  items: MemoryCardResponse[];
  total: number;
};

export type MemoryCardEntryResponse = {
  id: string;
  created_at_utc: string | null;
  local_date: string | null;
  source: string;
  raw_text: string;
  processed_status: string;
};

export type MemoryCardDetailResponse = MemoryCardResponse & {
  all_memories: MemoryCardMemoryResponse[];
  entries: MemoryCardEntryResponse[];
};
export type JobStatus =
  | "pending"
  | "retry"
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "dead_letter"
  | "canceled";

export type JobResponse = {
  id: string;
  status: JobStatus;
  entry_id: string | null;
  error: string | null;
  created_at_utc: string | null;
  queued_at_utc: string | null;
  started_at_utc: string | null;
  finished_at_utc: string | null;
};

export type JobsPageResponse = {
  items: JobResponse[];
  page: number;
  limit: number;
  total: number;
  has_next: boolean;
  next_cursor: string | null;
};

export type EntryResponse = {
  id: string;
  created_at_utc: string;
  local_date: string | null;
  local_time: string | null;
  source: string;
  raw_text: string;
  sensitivity: string;
  processed_status: string;
  processing_error: string | null;
  user_importance: number | null;
  importance_source: string | null;
  importance_updated_at: string | null;
};

export type EntriesPageResponse = {
  items: EntryResponse[];
  page: number;
  limit: number;
  total: number;
  has_next: boolean;
  next_cursor: string | null;
};

export type StatsResponse = {
  raw_entries: number;
  entities: number;
  memories: number;
  relationships: number;
  events: number;
  action_items: number;
  expenses: number;
  sources: number;
  uptime_seconds: number;
  vault_files: number;
};

export type AskResponse = {
  query: string;
  answer: string;
  context_size_chars: number;
};

export type ReportResponse = {
  report_type: "daily" | "weekly" | "monthly" | "person" | "place" | "topic" | string;
  query: string;
  markdown: string;
};

export type DeepHealthResponse = {
  status: "ok" | "degraded";
  uptime_seconds: number;
  version: string;
  checks: Record<string, { status: string; [key: string]: unknown }>;
};

export type AccountExportResponse = {
  exported_at_utc: string;
  user: Record<string, unknown>;
  tables: Record<string, unknown[]>;
};

export type ApiErrorBody = {
  error?: {
    code?: string;
    message?: string;
    request_id?: string;
    details?: unknown;
  };
};
