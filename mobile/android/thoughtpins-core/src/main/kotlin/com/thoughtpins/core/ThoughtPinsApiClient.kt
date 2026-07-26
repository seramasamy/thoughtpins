package com.thoughtpins.core

import kotlinx.serialization.encodeToString
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.net.URLEncoder
import java.nio.charset.StandardCharsets
import java.io.IOException
import java.time.Instant
import java.security.MessageDigest
import java.util.Base64
import java.util.UUID
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

class ThoughtPinsApiClient(
    private val baseUrl: String,
    private val sessionStore: SessionStore,
    private val http: OkHttpClient = OkHttpClient(),
    private val json: Json = Json { ignoreUnknownKeys = true },
) {
    private val refreshMutex = Mutex()

    suspend fun clientConfig(): ClientConfig =
        request("/v1/client-config", "GET", auth = false, bodyJson = null)

    suspend fun register(email: String? = null, phone: String? = null, password: String): RegisterResponse =
        request(
            "/v1/auth/register",
            "POST",
            auth = false,
            bodyJson = json.encodeToString(RegisterRequest(email, phone, password)),
        )

    suspend fun login(identifier: String, password: String): ApiSession {
        val token: TokenResponse = request(
            "/v1/auth/login",
            "POST",
            auth = false,
            bodyJson = json.encodeToString(LoginRequest(identifier, password)),
        )
        val session = ApiSession(token.accessToken, token.refreshToken)
        sessionStore.save(session)
        return session
    }

    suspend fun loginWithEmail(email: String, password: String): ApiSession = login(email, password)

    suspend fun loginWithPhone(phone: String, password: String): ApiSession = login(phone, password)

    suspend fun oauthLogin(
        provider: String,
        idToken: String,
        displayName: String? = null,
        authorizationCode: String? = null,
        redirectUri: String? = null,
        nonce: String? = null,
    ): ApiSession {
        val token: TokenResponse = request(
            "/v1/auth/oauth",
            "POST",
            auth = false,
            bodyJson = json.encodeToString(
                OAuthLoginRequest(provider, idToken, displayName, authorizationCode, redirectUri, nonce)
            ),
        )
        val session = ApiSession(token.accessToken, token.refreshToken)
        sessionStore.save(session)
        return session
    }

    suspend fun logout() {
        val refreshToken = sessionStore.load()?.refreshToken ?: return
        try {
            request<StatusResponse>(
                "/v1/auth/logout",
                "POST",
                auth = false,
                bodyJson = json.encodeToString(RefreshRequest(refreshToken)),
            )
        } finally {
            // Signing out locally must work even while the API is unavailable.
            sessionStore.save(null)
        }
    }

    suspend fun me(): MeResponse =
        request("/v1/me", "GET", auth = true, bodyJson = null)

    suspend fun chat(
        text: String,
        conversationId: String = "main",
        surface: String = "android",
        messageId: String? = null,
        includePrivate: Boolean? = null,
        confirmAction: Boolean? = null,
        pendingActionId: String? = null,
    ): ChatResponse {
        val resolvedMessageId = messageId ?: UUID.randomUUID().toString()
        return request(
            "/v1/chat",
            "POST",
            auth = true,
            bodyJson = json.encodeToString(
                ChatRequest(text, conversationId, surface, resolvedMessageId, includePrivate, confirmAction, pendingActionId),
            ),
            idempotencyKey = resolvedMessageId,
        )
    }

    suspend fun chatConversations(page: Int = 1, limit: Int = 20): ChatConversationsPageResponse =
        request("/v1/chat/conversations?page=$page&limit=$limit", "GET", auth = true, bodyJson = null)

    suspend fun chatMessages(conversationId: String, page: Int = 1, limit: Int = 80): ChatMessagesPageResponse =
        request("/v1/chat/conversations/${encode(conversationId)}/messages?page=$page&limit=$limit", "GET", auth = true, bodyJson = null)

    suspend fun ingest(
        text: String,
        userImportance: Int? = null,
        idempotencyKey: String? = null,
    ): IngestResponse {
        val messageId = idempotencyKey ?: UUID.randomUUID().toString()
        return request(
            "/v1/entries",
            "POST",
            auth = true,
            bodyJson = json.encodeToString(IngestRequest(text, userImportance, messageId)),
            idempotencyKey = messageId,
        )
    }

    suspend fun entries(page: Int = 1, limit: Int = 20): EntriesPageResponse =
        request("/v1/entries?page=$page&limit=$limit", "GET", auth = true, bodyJson = null)

    suspend fun updateEntryImportance(id: String, value: Int?): EntryResponse =
        request(
            "/v1/entries/${encode(id)}/importance",
            "PATCH",
            auth = true,
            bodyJson = json.encodeToString(EntryImportanceRequest(value)),
        )

    suspend fun deleteEntry(id: String): EntryDeleteResponse =
        request("/v1/entries/${encode(id)}", "DELETE", auth = true, bodyJson = null)

    suspend fun jobs(status: String = "", page: Int = 1, limit: Int = 20): JobsPageResponse {
        val suffix = if (status.isBlank()) "" else "&status=${encode(status)}"
        return request("/v1/jobs?page=$page&limit=$limit$suffix", "GET", auth = true, bodyJson = null)
    }

    suspend fun job(id: String): JobResponse =
        request("/v1/jobs/${encode(id)}", "GET", auth = true, bodyJson = null)

    suspend fun retryJob(id: String): JobResponse =
        request("/v1/jobs/${encode(id)}/retry", "POST", auth = true, bodyJson = "{}")

    suspend fun cancelJob(id: String): JobResponse =
        request("/v1/jobs/${encode(id)}/cancel", "POST", auth = true, bodyJson = "{}")

    suspend fun createLibrarySource(
        text: String? = null,
        url: String? = null,
        title: String? = null,
        author: String? = null,
        sourceType: String = "text",
    ): LibraryIngestResponse =
        request(
            "/v1/library",
            "POST",
            auth = true,
            bodyJson = json.encodeToString(LibraryIngestRequest(text, url, title, author, sourceType)),
        )

    suspend fun librarySources(limit: Int = 50): List<LibrarySourceResponse> =
        request("/v1/library?limit=$limit", "GET", auth = true, bodyJson = null)

    suspend fun librarySource(sourceRef: String): LibrarySourceResponse =
        request("/v1/library/${encode(sourceRef)}", "GET", auth = true, bodyJson = null)

    suspend fun memoryCards(section: String = "people", query: String = "", limit: Int = 24): MemoryCardsResponse =
        request(
            "/v1/memory/cards?section=${encode(section)}&q=${encode(query)}&limit=$limit",
            "GET",
            auth = true,
            bodyJson = null,
        )

    suspend fun memoryCard(id: String): MemoryCardDetailResponse =
        request("/v1/memory/cards/${encode(id)}", "GET", auth = true, bodyJson = null)

    suspend fun status(): StatsResponse =
        request("/v1/status", "GET", auth = true, bodyJson = null)

    suspend fun deepHealth(): DeepHealthResponse =
        request("/v1/health/deep", "GET", auth = true, bodyJson = null)

    suspend fun uploadFile(
        filename: String,
        contentBase64: String,
        mediaType: String? = null,
        destination: String = "auto",
        caption: String? = null,
        title: String? = null,
        sourceType: String? = null,
        conversationId: String = "uploads",
    ): UploadIngestResponse =
        request(
            "/v1/uploads",
            "POST",
            auth = true,
            bodyJson = json.encodeToString(
                UploadRequest(
                    filename = filename,
                    contentBase64 = contentBase64,
                    mediaType = mediaType,
                    destination = destination,
                    caption = caption,
                    title = title,
                    sourceType = sourceType,
                    surface = "android",
                    conversationId = conversationId,
                ),
            ),
        )

    suspend fun importObsidianVault(
        filename: String,
        contentBase64: String,
        mode: String = "auto",
        dryRun: Boolean = false,
    ): VaultImportResponse =
        request(
            "/v1/import/obsidian",
            "POST",
            auth = true,
            bodyJson = json.encodeToString(VaultImportRequest(filename, contentBase64, mode, dryRun)),
        )

    suspend fun importObsidianVaultResumable(
        filename: String,
        contentBase64: String,
        mode: String = "auto",
        conflictPolicy: String = "skip",
    ): VaultImportResponse {
        val preview = previewObsidianVaultResumable(filename, contentBase64, mode, conflictPolicy)
        return applyPreviewedVaultImport(preview.id, preview.conflictPolicy)
    }

    suspend fun previewObsidianVaultResumable(
        filename: String,
        contentBase64: String,
        mode: String = "auto",
        conflictPolicy: String = "skip",
    ): VaultImportSessionResponse {
        val archive = runCatching { Base64.getDecoder().decode(contentBase64) }
            .getOrElse { throw IOException("Vault archive is not valid base64", it) }
        if (archive.isEmpty()) throw IOException("Vault archive is empty")
        var transfer = createVaultImportUpload(filename, archive.size, mode, conflictPolicy)
        try {
            val chunkBytes = 512 * 1024
            while (transfer.receivedBytes < archive.size) {
                currentCoroutineContext().ensureActive()
                val start = transfer.receivedBytes
                val end = minOf(archive.size, start + chunkBytes)
                val chunk = archive.copyOfRange(start, end)
                val digest = MessageDigest.getInstance("SHA-256").digest(chunk).joinToString("") { "%02x".format(it) }
                transfer = appendVaultImportChunk(
                    transfer.id,
                    start,
                    Base64.getEncoder().encodeToString(chunk),
                    digest,
                )
            }
            transfer = previewVaultImport(transfer.id, conflictPolicy)
            return waitForVaultImport(transfer.id, "preview_ready")
        } catch (error: Throwable) {
            runCatching { cancelVaultImport(transfer.id) }
            throw error
        }
    }

    suspend fun applyPreviewedVaultImport(
        transferId: String,
        conflictPolicy: String,
    ): VaultImportResponse {
        applyVaultImport(transferId, conflictPolicy)
        val transfer = waitForVaultImport(transferId, "completed")
        return transfer.result ?: throw IOException("Completed vault import returned no result")
    }

    suspend fun createVaultImportUpload(
        filename: String,
        expectedBytes: Int,
        mode: String = "auto",
        conflictPolicy: String = "skip",
    ): VaultImportSessionResponse = request(
        "/v1/import/obsidian/uploads",
        "POST",
        auth = true,
        bodyJson = json.encodeToString(VaultUploadCreateRequest(filename, expectedBytes, mode, conflictPolicy)),
    )

    suspend fun appendVaultImportChunk(
        transferId: String,
        offset: Int,
        contentBase64: String,
        chunkSha256: String,
    ): VaultImportSessionResponse = request(
        "/v1/import/obsidian/uploads/${encode(transferId)}/chunks",
        "PUT",
        auth = true,
        bodyJson = json.encodeToString(VaultUploadChunkRequest(offset, contentBase64, chunkSha256)),
        idempotencyKey = "vault-chunk-$transferId-$offset-${chunkSha256.take(16)}",
    )

    suspend fun vaultImportSession(transferId: String): VaultImportSessionResponse =
        request("/v1/import/obsidian/uploads/${encode(transferId)}", "GET", auth = true, bodyJson = null)

    suspend fun previewVaultImport(transferId: String, conflictPolicy: String): VaultImportSessionResponse =
        request(
            "/v1/import/obsidian/uploads/${encode(transferId)}/preview",
            "POST",
            auth = true,
            bodyJson = json.encodeToString(VaultImportOperationRequest(conflictPolicy)),
        )

    suspend fun applyVaultImport(transferId: String, conflictPolicy: String): VaultImportSessionResponse =
        request(
            "/v1/import/obsidian/uploads/${encode(transferId)}/apply",
            "POST",
            auth = true,
            bodyJson = json.encodeToString(VaultImportOperationRequest(conflictPolicy)),
        )

    suspend fun cancelVaultImport(transferId: String): VaultImportSessionResponse =
        request("/v1/import/obsidian/uploads/${encode(transferId)}/cancel", "POST", auth = true, bodyJson = "{}")

    private suspend fun waitForVaultImport(transferId: String, target: String): VaultImportSessionResponse {
        repeat(2_400) {
            currentCoroutineContext().ensureActive()
            val transfer = vaultImportSession(transferId)
            if (transfer.status == target) return transfer
            if (transfer.status in setOf("failed", "canceled", "expired")) {
                throw IOException(transfer.error ?: "Vault import ended with status ${transfer.status}")
            }
            delay(500)
        }
        throw IOException("Vault import did not finish before the client timeout")
    }

    suspend fun preferences(): PreferencesResponse =
        request("/v1/preferences", "GET", auth = true, bodyJson = null)

    suspend fun updatePreferences(preferences: PreferencesUpdateRequest): PreferencesResponse =
        request("/v1/preferences", "PATCH", auth = true, bodyJson = json.encodeToString(preferences))

    suspend fun voiceArchive(): VoiceArchiveStatusResponse =
        request("/v1/voice-archive", "GET", auth = true, bodyJson = null)

    suspend fun enableVoiceArchive(consent: VoiceArchiveConsentRequest): VoiceArchiveStatusResponse =
        request("/v1/voice-archive/consent", "POST", auth = true, bodyJson = json.encodeToString(consent))

    suspend fun disableVoiceArchive(): VoiceArchiveStatusResponse =
        request("/v1/voice-archive/consent", "DELETE", auth = true, bodyJson = null)

    suspend fun deleteVoiceArchive(): VoiceArchiveDeleteResponse =
        request(
            "/v1/voice-archive",
            "DELETE",
            auth = true,
            bodyJson = json.encodeToString(VoiceArchiveDeleteRequest("DELETE VOICE ARCHIVE")),
        )

    suspend fun acceptLegalDocument(document: String, version: String): PreferencesResponse =
        request(
            "/v1/legal/acceptances",
            "POST",
            auth = true,
            bodyJson = json.encodeToString(LegalAcceptanceRequest(document, version)),
        )

    suspend fun createSafetyReport(report: SafetyReportRequest): SafetyReportResponse =
        request("/v1/safety/reports", "POST", auth = true, bodyJson = json.encodeToString(report))

    suspend fun devices(): DevicesPageResponse =
        request("/v1/devices", "GET", auth = true, bodyJson = null)

    suspend fun registerDevice(device: DeviceRegistration): DeviceResponse =
        request("/v1/devices", "POST", auth = true, bodyJson = json.encodeToString(device))

    suspend fun revokeDevice(installationId: String): DeviceResponse =
        request("/v1/devices/${encode(installationId)}", "DELETE", auth = true, bodyJson = null)

    suspend fun sessions(): SessionsPageResponse =
        request("/v1/sessions", "GET", auth = true, bodyJson = null)

    suspend fun revokeSession(id: String): SessionResponse =
        request("/v1/sessions/${encode(id)}", "DELETE", auth = true, bodyJson = null)

    suspend fun revokeOtherSessions(): SessionRevocationResponse =
        request("/v1/sessions/revoke-others", "POST", auth = true, bodyJson = "{}")

    suspend fun exportAccount(): AccountExportResponse =
        request("/v1/export", "GET", auth = true, bodyJson = null)

    suspend fun deleteAccount(): AccountDeletionResponse {
        val response: AccountDeletionResponse = request(
            "/v1/me",
            "DELETE",
            auth = true,
            bodyJson = json.encodeToString(DeleteAccountRequest("DELETE")),
        )
        sessionStore.save(null)
        return response
    }

    suspend fun syncQueuedDrafts(queue: DraftQueue): DraftSyncSummary {
        val results = mutableListOf<DraftSyncResult>()
        for (draft in queue.pending()) {
            val submitting = draft.copy(status = DraftStatus.SUBMITTING, attemptCount = draft.attemptCount + 1, lastError = null, updatedAtUtc = Instant.now().toString())
            queue.update(submitting)
            try {
                val response = ingest(submitting.text, idempotencyKey = draft.id)
                val synced = submitting.copy(status = DraftStatus.SYNCED, entryId = response.entryId, jobId = response.jobId, updatedAtUtc = Instant.now().toString())
                queue.update(synced)
                results += DraftSyncResult(draft.id, DraftStatus.SYNCED, response.entryId, response.jobId, null)
            } catch (error: Throwable) {
                val failed = submitting.copy(status = DraftStatus.FAILED, lastError = error.message ?: "Sync failed", updatedAtUtc = Instant.now().toString())
                queue.update(failed)
                results += DraftSyncResult(draft.id, DraftStatus.FAILED, null, null, failed.lastError)
            }
        }
        return DraftSyncSummary(results)
    }

    private suspend inline fun <reified T> request(
        path: String,
        method: String,
        auth: Boolean,
        bodyJson: String?,
        idempotencyKey: String? = null,
    ): T {
        val mutationMethods = setOf("POST", "PUT", "PATCH", "DELETE")
        val resolvedIdempotencyKey = idempotencyKey ?: if (auth && method in mutationMethods) UUID.randomUUID().toString() else null
        val attemptedAccessToken = if (auth) sessionStore.load()?.accessToken else null
        var response = execute(path, method, auth, bodyJson, resolvedIdempotencyKey)
        if (response.code == 401 && auth && refreshSession(attemptedAccessToken)) {
            response.close()
            response = execute(path, method, auth, bodyJson, resolvedIdempotencyKey)
        }
        response.use { finalResponse ->
            val responseText = finalResponse.body.string()
            if (!finalResponse.isSuccessful) {
                val message = sanitizedErrorMessage(responseText)
                throw IOException("HTTP ${finalResponse.code}${message?.let { ": $it" } ?: ""}")
            }
            if (T::class == UnitEnvelope::class) {
                return UnitEnvelope as T
            }
            return json.decodeFromString(responseText)
        }
    }

    private suspend fun execute(
        path: String,
        method: String,
        auth: Boolean,
        bodyJson: String?,
        idempotencyKey: String?,
    ): okhttp3.Response {
        val session = if (auth) sessionStore.load() else null
        return withContext(Dispatchers.IO) {
            val requestBody = when {
                bodyJson != null -> bodyJson.toRequestBody("application/json".toMediaType())
                method == "POST" || method == "PATCH" -> "{}".toRequestBody("application/json".toMediaType())
                else -> null
            }
            val builder = Request.Builder()
                .url(baseUrl.trimEnd('/') + path)
                .method(method, requestBody)
                .header("Content-Type", "application/json")
                .header("Cache-Control", "no-store")
                .header("Pragma", "no-cache")
                .header("X-Request-ID", UUID.randomUUID().toString())
            session?.accessToken?.let { builder.header("Authorization", "Bearer $it") }
            idempotencyKey?.let { builder.header("Idempotency-Key", it) }
            http.newCall(builder.build()).execute()
        }
    }

    private suspend fun refreshSession(attemptedAccessToken: String?): Boolean = refreshMutex.withLock {
        val current = sessionStore.load() ?: return@withLock false
        if (attemptedAccessToken != null && current.accessToken != attemptedAccessToken) {
            return@withLock true
        }
        val response = execute(
            "/v1/auth/refresh",
            "POST",
            auth = false,
            bodyJson = json.encodeToString(RefreshRequest(current.refreshToken)),
            idempotencyKey = null,
        )
        response.use {
            val responseText = it.body.string()
            if (!it.isSuccessful) {
                val message = sanitizedErrorMessage(responseText)
                throw IOException("HTTP ${it.code}${message?.let { text -> ": $text" } ?: ""}")
            }
            val token: TokenResponse = json.decodeFromString(responseText)
            sessionStore.save(ApiSession(token.accessToken, token.refreshToken))
            true
        }
    }

    private fun sanitizedErrorMessage(responseText: String): String? =
        runCatching { json.decodeFromString<ErrorEnvelope>(responseText).error.message.trim().take(512) }
            .getOrNull()
            ?.ifEmpty { null }

    private fun encode(value: String): String = URLEncoder.encode(value, StandardCharsets.UTF_8.toString())
}

object UnitEnvelope

@Serializable
private data class RegisterRequest(val email: String? = null, val phone: String? = null, val password: String)

@Serializable
private data class LoginRequest(val identifier: String, val password: String)

@Serializable
private data class OAuthLoginRequest(
    val provider: String,
    @SerialName("id_token") val idToken: String,
    @SerialName("display_name") val displayName: String? = null,
    @SerialName("authorization_code") val authorizationCode: String? = null,
    @SerialName("redirect_uri") val redirectUri: String? = null,
    val nonce: String? = null,
)

@Serializable
private data class RefreshRequest(@SerialName("refresh_token") val refreshToken: String)

@Serializable
private data class ErrorEnvelope(val error: ErrorBody)

@Serializable
private data class ErrorBody(val message: String)

@Serializable
private data class IngestRequest(
    val text: String,
    @SerialName("user_importance") val userImportance: Int? = null,
    @SerialName("message_id") val messageId: String,
)

@Serializable
private data class EntryImportanceRequest(
    @SerialName("user_importance") val userImportance: Int?,
)

@Serializable
private data class ChatRequest(
    val text: String,
    @SerialName("conversation_id") val conversationId: String = "main",
    val surface: String = "android",
    @SerialName("message_id") val messageId: String? = null,
    @SerialName("include_private") val includePrivate: Boolean? = null,
    @SerialName("confirm_action") val confirmAction: Boolean? = null,
    @SerialName("pending_action_id") val pendingActionId: String? = null,
)

@Serializable
private data class LibraryIngestRequest(
    val text: String? = null,
    val url: String? = null,
    val title: String? = null,
    val author: String? = null,
    @SerialName("source_type") val sourceType: String = "text",
)

@Serializable
private data class LegalAcceptanceRequest(val document: String, val version: String)

@Serializable
private data class DeleteAccountRequest(val confirm: String)

@Serializable
private data class UploadRequest(
    val filename: String,
    @SerialName("content_base64") val contentBase64: String,
    @SerialName("media_type") val mediaType: String? = null,
    val destination: String = "auto",
    val caption: String? = null,
    val title: String? = null,
    @SerialName("source_type") val sourceType: String? = null,
    val surface: String = "android",
    @SerialName("conversation_id") val conversationId: String = "uploads",
)

@Serializable
private data class VaultImportRequest(
    val filename: String,
    @SerialName("content_base64") val contentBase64: String,
    val mode: String = "auto",
    @SerialName("dry_run") val dryRun: Boolean = false,
)

@Serializable
private data class VaultUploadCreateRequest(
    val filename: String,
    @SerialName("expected_bytes") val expectedBytes: Int,
    val mode: String = "auto",
    @SerialName("conflict_policy") val conflictPolicy: String = "skip",
)

@Serializable
private data class VaultUploadChunkRequest(
    val offset: Int,
    @SerialName("content_base64") val contentBase64: String,
    @SerialName("chunk_sha256") val chunkSha256: String,
)

@Serializable
private data class VaultImportOperationRequest(
    @SerialName("conflict_policy") val conflictPolicy: String,
)
