package com.thoughtpins.core

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

@Serializable
data class ApiSession(
    val accessToken: String,
    val refreshToken: String,
)

@Serializable
data class TokenResponse(
    @SerialName("access_token") val accessToken: String,
    @SerialName("refresh_token") val refreshToken: String,
    @SerialName("token_type") val tokenType: String,
    @SerialName("expires_in") val expiresIn: Int,
)

@Serializable
data class ClientConfig(
    @SerialName("app_name") val appName: String,
    @SerialName("api_version") val apiVersion: String,
    @SerialName("auth_required") val authRequired: Boolean,
    @SerialName("registration_locked") val registrationLocked: Boolean,
    @SerialName("oauth_google_enabled") val oauthGoogleEnabled: Boolean = false,
    @SerialName("oauth_apple_enabled") val oauthAppleEnabled: Boolean = false,
    @SerialName("voice_archive_enabled") val voiceArchiveEnabled: Boolean = false,
    @SerialName("memory_context_mode") val memoryContextMode: String? = null,
    @SerialName("privacy_policy_url") val privacyPolicyUrl: String? = null,
    @SerialName("terms_url") val termsUrl: String? = null,
    @SerialName("support_url") val supportUrl: String? = null,
    @SerialName("account_deletion_url") val accountDeletionUrl: String? = null,
    @SerialName("ai_disclosure_url") val aiDisclosureUrl: String? = null,
    @SerialName("legal_document_version") val legalDocumentVersion: String = "2026-07-13",
    @SerialName("minimum_supported_clients") val minimumSupportedClients: Map<String, String>,
    @SerialName("recommended_clients") val recommendedClients: Map<String, String>,
    @SerialName("store_urls") val storeUrls: Map<String, String?>,
    @SerialName("maintenance_mode") val maintenanceMode: Boolean = false,
    @SerialName("maintenance_message") val maintenanceMessage: String? = null,
    @SerialName("maintenance_retry_after_seconds") val maintenanceRetryAfterSeconds: Int? = null,
    @SerialName("maintenance_allow_reads") val maintenanceAllowReads: Boolean = true,
)

@Serializable
data class IngestResponse(
    val status: String,
    @SerialName("entry_id") val entryId: String,
    @SerialName("job_id") val jobId: String? = null,
    @SerialName("user_importance") val userImportance: Int? = null,
)

@Serializable
data class UploadIngestResponse(
    val status: String,
    @SerialName("route_type") val routeType: String,
    val filename: String,
    @SerialName("media_kind") val mediaKind: String,
    val destination: String,
    @SerialName("extraction_status") val extractionStatus: String,
    @SerialName("extracted_chars") val extractedChars: Int = 0,
    @SerialName("attachment_saved") val attachmentSaved: Boolean = false,
    @SerialName("attachment_ref") val attachmentRef: String? = null,
    @SerialName("voice_asset_id") val voiceAssetId: String? = null,
    val title: String? = null,
    @SerialName("entry_id") val entryId: String? = null,
    @SerialName("job_id") val jobId: String? = null,
    @SerialName("document_id") val documentId: String? = null,
    val error: String? = null,
)

@Serializable
data class VaultImportResponse(
    val status: String,
    val format: String,
    val mode: String,
    @SerialName("thoughtpins_export") val thoughtpinsExport: Boolean,
    @SerialName("dry_run") val dryRun: Boolean,
    @SerialName("archive_sha256") val archiveSha256: String = "",
    @SerialName("files_discovered") val filesDiscovered: Int,
    @SerialName("notes_discovered") val notesDiscovered: Int,
    @SerialName("attachments_skipped") val attachmentsSkipped: Int,
    @SerialName("structural_files_skipped") val structuralFilesSkipped: Int,
    @SerialName("canvases_discovered") val canvasesDiscovered: Int,
    @SerialName("canvas_documents_imported") val canvasDocumentsImported: Int,
    @SerialName("journal_notes") val journalNotes: Int,
    @SerialName("library_notes") val libraryNotes: Int,
    @SerialName("journal_jobs_queued") val journalJobsQueued: Int,
    @SerialName("library_documents_imported") val libraryDocumentsImported: Int,
    @SerialName("new_notes") val newNotes: Int = 0,
    @SerialName("changed_notes") val changedNotes: Int = 0,
    @SerialName("unchanged_notes") val unchangedNotes: Int = 0,
    val conflicts: Int = 0,
    val duplicates: Int,
    val skipped: Int,
    val imported: Int,
    val warnings: List<String> = emptyList(),
    val errors: List<String> = emptyList(),
    @SerialName("job_ids") val jobIds: List<String> = emptyList(),
    @SerialName("document_ids") val documentIds: List<String> = emptyList(),
    @SerialName("preview_items") val previewItems: List<VaultImportPreviewItem> = emptyList(),
)

@Serializable
data class VaultImportPreviewItem(
    val path: String,
    val title: String,
    val kind: String,
    val state: String,
    val action: String,
)

@Serializable
data class VaultImportSessionResponse(
    val id: String,
    val status: String,
    val operation: String? = null,
    val filename: String,
    val mode: String,
    @SerialName("conflict_policy") val conflictPolicy: String,
    @SerialName("expected_bytes") val expectedBytes: Int,
    @SerialName("received_bytes") val receivedBytes: Int,
    @SerialName("archive_sha256") val archiveSha256: String? = null,
    @SerialName("progress_current") val progressCurrent: Int,
    @SerialName("progress_total") val progressTotal: Int,
    @SerialName("progress_percent") val progressPercent: Double,
    @SerialName("progress_stage") val progressStage: String,
    @SerialName("cancel_requested") val cancelRequested: Boolean,
    val result: VaultImportResponse? = null,
    val error: String? = null,
    @SerialName("created_at_utc") val createdAtUtc: String? = null,
    @SerialName("updated_at_utc") val updatedAtUtc: String? = null,
    @SerialName("finished_at_utc") val finishedAtUtc: String? = null,
    @SerialName("expires_at_utc") val expiresAtUtc: String? = null,
)

@Serializable
data class DeviceRegistration(
    @SerialName("installation_id") val installationId: String,
    val platform: String = "android",
    @SerialName("device_name") val deviceName: String? = null,
    @SerialName("app_version") val appVersion: String? = null,
    @SerialName("build_number") val buildNumber: String? = null,
    @SerialName("os_version") val osVersion: String? = null,
    val locale: String? = null,
    val timezone: String? = null,
    @SerialName("push_provider") val pushProvider: String? = null,
    @SerialName("push_token") val pushToken: String? = null,
    @SerialName("notifications_enabled") val notificationsEnabled: Boolean = false,
)


@Serializable
data class MemoryCardMemoryResponse(
    val id: String? = null,
    @SerialName("entry_id") val entryId: String? = null,
    val date: String? = null,
    val type: String,
    val text: String,
    val confidence: String? = null,
)

@Serializable
data class MemoryCardRelationshipResponse(
    val type: String,
    val other: String,
    val confidence: String? = null,
    @SerialName("evidence_count") val evidenceCount: Int = 1,
)

@Serializable
data class MemoryCardSourceResponse(
    val id: String,
    val title: String,
    @SerialName("source_type") val sourceType: String,
    val status: String,
    @SerialName("source_url") val sourceUrl: String? = null,
    @SerialName("obsidian_path") val obsidianPath: String? = null,
)

@Serializable
data class MemoryCardTimelineResponse(
    val date: String? = null,
    val label: String,
    val source: String? = null,
)

@Serializable
data class MemoryCardResponse(
    val id: String,
    val name: String,
    val type: String,
    val subtitle: String? = null,
    val aliases: List<String> = emptyList(),
    val attributes: List<JsonElement> = emptyList(),
    @SerialName("memory_count") val memoryCount: Int = 0,
    @SerialName("mention_count") val mentionCount: Int = 0,
    @SerialName("relationship_count") val relationshipCount: Int = 0,
    @SerialName("first_seen_at_utc") val firstSeenAtUtc: String? = null,
    @SerialName("last_seen") val lastSeen: String? = null,
    val statline: Map<String, JsonElement> = emptyMap(),
    @SerialName("recent_memories") val recentMemories: List<MemoryCardMemoryResponse> = emptyList(),
    val relationships: List<MemoryCardRelationshipResponse> = emptyList(),
    @SerialName("source_documents") val sourceDocuments: List<MemoryCardSourceResponse> = emptyList(),
    val timeline: List<MemoryCardTimelineResponse> = emptyList(),
    val provenance: Map<String, JsonElement> = emptyMap(),
    @SerialName("ask_prompt") val askPrompt: String? = null,
    @SerialName("obsidian_path") val obsidianPath: String? = null,
)

@Serializable
data class MemoryCardsResponse(
    val section: String,
    val query: String = "",
    val sections: Map<String, List<String>> = emptyMap(),
    val items: List<MemoryCardResponse> = emptyList(),
    val total: Int = 0,
)

@Serializable
data class MemoryCardEntryResponse(
    val id: String,
    @SerialName("created_at_utc") val createdAtUtc: String? = null,
    @SerialName("local_date") val localDate: String? = null,
    val source: String,
    @SerialName("raw_text") val rawText: String,
    @SerialName("processed_status") val processedStatus: String,
)

@Serializable
data class MemoryCardDetailResponse(
    val id: String,
    val name: String,
    val type: String,
    val subtitle: String? = null,
    val aliases: List<String> = emptyList(),
    val attributes: List<JsonElement> = emptyList(),
    @SerialName("memory_count") val memoryCount: Int = 0,
    @SerialName("mention_count") val mentionCount: Int = 0,
    @SerialName("relationship_count") val relationshipCount: Int = 0,
    @SerialName("first_seen_at_utc") val firstSeenAtUtc: String? = null,
    @SerialName("last_seen") val lastSeen: String? = null,
    val statline: Map<String, JsonElement> = emptyMap(),
    @SerialName("recent_memories") val recentMemories: List<MemoryCardMemoryResponse> = emptyList(),
    val relationships: List<MemoryCardRelationshipResponse> = emptyList(),
    @SerialName("source_documents") val sourceDocuments: List<MemoryCardSourceResponse> = emptyList(),
    val timeline: List<MemoryCardTimelineResponse> = emptyList(),
    val provenance: Map<String, JsonElement> = emptyMap(),
    @SerialName("ask_prompt") val askPrompt: String? = null,
    @SerialName("obsidian_path") val obsidianPath: String? = null,
    @SerialName("all_memories") val allMemories: List<MemoryCardMemoryResponse> = emptyList(),
    val entries: List<MemoryCardEntryResponse> = emptyList(),
)

@Serializable
data class CaptureDraft(
    val id: String,
    val text: String,
    val status: DraftStatus,
    val createdAtUtc: String,
    val updatedAtUtc: String,
    val attemptCount: Int,
    val lastError: String? = null,
    val entryId: String? = null,
    val jobId: String? = null,
)

@Serializable
enum class DraftStatus {
    DRAFT,
    QUEUED,
    SUBMITTING,
    FAILED,
    SYNCED,
}

@Serializable
data class RegisterResponse(
    val status: String,
    @SerialName("user_id") val userId: String,
    @SerialName("api_key") val apiKey: String? = null,
)

@Serializable
data class StatusResponse(val status: String)

@Serializable
data class MeResponse(
    val id: String,
    val email: String? = null,
    val phone: String? = null,
    @SerialName("display_name") val displayName: String? = null,
    @SerialName("is_admin") val isAdmin: Boolean = false,
    @SerialName("auth_method") val authMethod: String,
    @SerialName("created_at_utc") val createdAtUtc: String? = null,
    @SerialName("last_login_utc") val lastLoginUtc: String? = null,
)

@Serializable
data class ChatResponse(
    val status: String,
    @SerialName("route_type") val routeType: String,
    val reply: String,
    @SerialName("entry_id") val entryId: String? = null,
    @SerialName("job_id") val jobId: String? = null,
    @SerialName("document_id") val documentId: String? = null,
    @SerialName("requires_confirmation") val requiresConfirmation: Boolean = false,
    @SerialName("confirmation_prompt") val confirmationPrompt: String? = null,
    @SerialName("context_size_chars") val contextSizeChars: Int = 0,
    val metadata: Map<String, JsonElement> = emptyMap(),
)

@Serializable
data class ChatConversationResponse(
    val id: String,
    @SerialName("conversation_key") val conversationKey: String,
    val surface: String,
    val title: String? = null,
    @SerialName("created_at_utc") val createdAtUtc: String? = null,
    @SerialName("updated_at_utc") val updatedAtUtc: String? = null,
    @SerialName("last_message_at_utc") val lastMessageAtUtc: String? = null,
)

@Serializable
data class ChatConversationsPageResponse(
    val items: List<ChatConversationResponse> = emptyList(),
    val page: Int,
    val limit: Int,
    val total: Int,
    @SerialName("has_next") val hasNext: Boolean = false,
    @SerialName("next_cursor") val nextCursor: String? = null,
)

@Serializable
data class ChatMessageResponse(
    val id: String,
    @SerialName("conversation_id") val conversationId: String,
    val role: String,
    val text: String,
    @SerialName("route_type") val routeType: String? = null,
    val status: String? = null,
    @SerialName("entry_id") val entryId: String? = null,
    @SerialName("job_id") val jobId: String? = null,
    @SerialName("document_id") val documentId: String? = null,
    @SerialName("created_at_utc") val createdAtUtc: String? = null,
    val metadata: Map<String, JsonElement> = emptyMap(),
)

@Serializable
data class ChatMessagesPageResponse(
    val items: List<ChatMessageResponse> = emptyList(),
    val page: Int,
    val limit: Int,
    val total: Int,
    @SerialName("has_next") val hasNext: Boolean = false,
    @SerialName("next_cursor") val nextCursor: String? = null,
)

@Serializable
data class EntryResponse(
    val id: String,
    @SerialName("created_at_utc") val createdAtUtc: String,
    @SerialName("local_date") val localDate: String? = null,
    @SerialName("local_time") val localTime: String? = null,
    val source: String,
    @SerialName("raw_text") val rawText: String,
    val sensitivity: String,
    @SerialName("processed_status") val processedStatus: String,
    @SerialName("processing_error") val processingError: String? = null,
    @SerialName("user_importance") val userImportance: Int? = null,
    @SerialName("importance_source") val importanceSource: String? = null,
    @SerialName("importance_updated_at") val importanceUpdatedAt: String? = null,
)

@Serializable
data class EntriesPageResponse(
    val items: List<EntryResponse> = emptyList(),
    val page: Int,
    val limit: Int,
    val total: Int,
    @SerialName("has_next") val hasNext: Boolean = false,
    @SerialName("next_cursor") val nextCursor: String? = null,
)

@Serializable
data class EntryDeleteResponse(
    val status: String,
    @SerialName("entry_id") val entryId: String,
)

@Serializable
data class LibraryIngestResponse(
    @SerialName("document_id") val documentId: String,
    @SerialName("raw_entry_id") val rawEntryId: String,
    val title: String,
    @SerialName("source_type") val sourceType: String,
    val status: String,
    val chunks: Int = 0,
    val memories: Int = 0,
    @SerialName("source_url") val sourceUrl: String? = null,
    val duplicate: Boolean = false,
    val error: String? = null,
    @SerialName("access_method") val accessMethod: String? = null,
    @SerialName("rights_basis") val rightsBasis: String? = null,
    @SerialName("paywall_detected") val paywallDetected: Boolean = false,
)

@Serializable
data class LibrarySourceResponse(
    val id: String,
    val title: String,
    @SerialName("source_type") val sourceType: String,
    val status: String,
    @SerialName("source_url") val sourceUrl: String? = null,
    @SerialName("original_url") val originalUrl: String? = null,
    @SerialName("canonical_url") val canonicalUrl: String? = null,
    @SerialName("source_domain") val sourceDomain: String? = null,
    val author: String? = null,
    @SerialName("published_at") val publishedAt: String? = null,
    val publisher: String? = null,
    val topics: List<String> = emptyList(),
    @SerialName("key_concepts") val keyConcepts: List<String> = emptyList(),
    @SerialName("access_method") val accessMethod: String? = null,
    @SerialName("rights_basis") val rightsBasis: String? = null,
    @SerialName("fetch_status") val fetchStatus: String? = null,
    @SerialName("paywall_detected") val paywallDetected: Boolean = false,
    @SerialName("retrieval_quality_score") val retrievalQualityScore: Double? = null,
    val summary: String? = null,
    @SerialName("created_at_utc") val createdAtUtc: String? = null,
    val chunks: Int = 0,
)

@Serializable
data class JobResponse(
    val id: String,
    val status: String,
    @SerialName("entry_id") val entryId: String? = null,
    val error: String? = null,
    @SerialName("created_at_utc") val createdAtUtc: String? = null,
    @SerialName("started_at_utc") val startedAtUtc: String? = null,
    @SerialName("finished_at_utc") val finishedAtUtc: String? = null,
)

@Serializable
data class JobsPageResponse(
    val items: List<JobResponse> = emptyList(),
    val page: Int,
    val limit: Int,
    val total: Int,
    @SerialName("has_next") val hasNext: Boolean = false,
    @SerialName("next_cursor") val nextCursor: String? = null,
)

@Serializable
data class StatsResponse(
    @SerialName("raw_entries") val rawEntries: Int,
    val entities: Int,
    val memories: Int,
    val relationships: Int,
    val events: Int,
    @SerialName("action_items") val actionItems: Int,
    val expenses: Int,
    val sources: Int,
    @SerialName("uptime_seconds") val uptimeSeconds: Double,
    @SerialName("vault_files") val vaultFiles: Int,
)

@Serializable
data class DeepHealthResponse(
    val status: String,
    @SerialName("uptime_seconds") val uptimeSeconds: Double,
    val version: String,
    val checks: Map<String, JsonElement> = emptyMap(),
)

@Serializable
data class LegalAcceptance(
    val version: String,
    @SerialName("accepted_at_utc") val acceptedAtUtc: String,
)

@Serializable
data class PreferencesResponse(
    @SerialName("notifications_enabled") val notificationsEnabled: Boolean = false,
    @SerialName("reminder_hour_local") val reminderHourLocal: Int? = null,
    val timezone: String? = null,
    @SerialName("private_entries_in_ask") val privateEntriesInAsk: Boolean = false,
    @SerialName("weekly_digest_enabled") val weeklyDigestEnabled: Boolean = false,
    @SerialName("product_updates_enabled") val productUpdatesEnabled: Boolean = false,
    @SerialName("preferred_name") val preferredName: String? = null,
    @SerialName("response_style") val responseStyle: String = "friendly",
    @SerialName("importance_prompts_enabled") val importancePromptsEnabled: Boolean = false,
    @SerialName("legal_acceptances") val legalAcceptances: Map<String, LegalAcceptance> = emptyMap(),
    @SerialName("updated_at_utc") val updatedAtUtc: String? = null,
)

@Serializable
data class PreferencesUpdateRequest(
    @SerialName("notifications_enabled") val notificationsEnabled: Boolean? = null,
    @SerialName("reminder_hour_local") val reminderHourLocal: Int? = null,
    val timezone: String? = null,
    @SerialName("private_entries_in_ask") val privateEntriesInAsk: Boolean? = null,
    @SerialName("weekly_digest_enabled") val weeklyDigestEnabled: Boolean? = null,
    @SerialName("product_updates_enabled") val productUpdatesEnabled: Boolean? = null,
    @SerialName("preferred_name") val preferredName: String? = null,
    @SerialName("response_style") val responseStyle: String? = null,
    @SerialName("importance_prompts_enabled") val importancePromptsEnabled: Boolean? = null,
)

@Serializable
data class VoiceArchiveStatusResponse(
    val enabled: Boolean = false,
    @SerialName("consent_version") val consentVersion: String? = null,
    @SerialName("current_consent_version") val currentConsentVersion: String,
    @SerialName("consented_at_utc") val consentedAtUtc: String? = null,
    @SerialName("asset_count") val assetCount: Int = 0,
    @SerialName("original_bytes") val originalBytes: Long = 0,
    @SerialName("stored_bytes") val storedBytes: Long = 0,
    @SerialName("default_processing") val defaultProcessing: String = "ephemeral",
    @SerialName("retention_purpose") val retentionPurpose: String = "personal_voice_features",
    @SerialName("derived_voice_data_created") val derivedVoiceDataCreated: Boolean = false,
)

@Serializable
data class VoiceArchiveConsentRequest(
    @SerialName("retain_recordings") val retainRecordings: Boolean,
    @SerialName("acknowledge_sensitive_audio") val acknowledgeSensitiveAudio: Boolean,
    @SerialName("acknowledge_personal_use_only") val acknowledgePersonalUseOnly: Boolean,
    @SerialName("acknowledge_deletion_available") val acknowledgeDeletionAvailable: Boolean,
)

@Serializable
data class VoiceArchiveDeleteRequest(val confirm: String)

@Serializable
data class VoiceArchiveDeleteResponse(
    val status: String,
    val deleted: Map<String, Int> = emptyMap(),
)

@Serializable
data class SafetyReportRequest(
    val category: String,
    val summary: String,
    @SerialName("target_type") val targetType: String? = "general",
    @SerialName("target_id") val targetId: String? = null,
    val source: String = "android",
    val metadata: Map<String, JsonElement> = emptyMap(),
)

@Serializable
data class SafetyReportResponse(
    val id: String,
    val status: String,
    val category: String,
    @SerialName("created_at_utc") val createdAtUtc: String? = null,
    @SerialName("support_channel") val supportChannel: String,
)

@Serializable
data class DeviceResponse(
    val id: String,
    @SerialName("installation_id") val installationId: String,
    val platform: String,
    @SerialName("device_name") val deviceName: String? = null,
    @SerialName("app_version") val appVersion: String? = null,
    @SerialName("build_number") val buildNumber: String? = null,
    @SerialName("os_version") val osVersion: String? = null,
    val locale: String? = null,
    val timezone: String? = null,
    @SerialName("push_provider") val pushProvider: String? = null,
    @SerialName("push_token_present") val pushTokenPresent: Boolean = false,
    @SerialName("notifications_enabled") val notificationsEnabled: Boolean = false,
    @SerialName("created_at_utc") val createdAtUtc: String? = null,
    @SerialName("last_seen_at_utc") val lastSeenAtUtc: String? = null,
    @SerialName("revoked_at_utc") val revokedAtUtc: String? = null,
)

@Serializable
data class DevicesPageResponse(
    val items: List<DeviceResponse> = emptyList(),
    val total: Int = 0,
)

@Serializable
data class SessionResponse(
    val id: String,
    val current: Boolean = false,
    @SerialName("created_at_utc") val createdAtUtc: String? = null,
    @SerialName("expires_at_utc") val expiresAtUtc: String? = null,
    @SerialName("revoked_at_utc") val revokedAtUtc: String? = null,
    @SerialName("user_agent") val userAgent: String? = null,
    @SerialName("ip_address") val ipAddress: String? = null,
)

@Serializable
data class SessionsPageResponse(
    val items: List<SessionResponse> = emptyList(),
    val total: Int = 0,
)

@Serializable
data class SessionRevocationResponse(
    val status: String,
    val count: Int = 0,
)

@Serializable
data class AccountExportResponse(
    @SerialName("exported_at_utc") val exportedAtUtc: String,
    val user: Map<String, JsonElement> = emptyMap(),
    val tables: Map<String, List<JsonElement>> = emptyMap(),
)

@Serializable
data class AccountDeletionResponse(
    val status: String,
    val deleted: Map<String, Int> = emptyMap(),
)

@Serializable
data class DraftSyncResult(
    val draftId: String,
    val status: DraftStatus,
    val entryId: String? = null,
    val jobId: String? = null,
    val error: String? = null,
)

@Serializable
data class DraftSyncSummary(
    val results: List<DraftSyncResult> = emptyList(),
) {
    val attempted: Int get() = results.size
    val synced: Int get() = results.count { it.status == DraftStatus.SYNCED }
    val failed: Int get() = results.count { it.status == DraftStatus.FAILED }
}
