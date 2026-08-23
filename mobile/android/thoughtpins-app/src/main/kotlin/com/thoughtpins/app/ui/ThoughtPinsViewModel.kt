package com.thoughtpins.app.ui

import android.util.Base64
import android.provider.Settings as AndroidSystemSettings
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.StartOffset
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Chat
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.outlined.CalendarMonth
import androidx.compose.material.icons.outlined.People
import androidx.compose.material.icons.outlined.Place
import androidx.compose.material.icons.outlined.PushPin
import androidx.compose.material.icons.outlined.Star
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.Checkbox
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Shapes
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.withTransform
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.thoughtpins.core.ClientConfig
import com.thoughtpins.core.DraftQueue
import com.thoughtpins.core.EntryResponse
import com.thoughtpins.core.LibrarySourceResponse
import com.thoughtpins.core.MeResponse
import com.thoughtpins.core.MemoryCardResponse
import com.thoughtpins.core.PreferencesUpdateRequest
import com.thoughtpins.core.ThoughtPinsApiClient
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch


class ThoughtPinsViewModel(
    private val api: ThoughtPinsApiClient,
    private val draftQueue: DraftQueue,
    private val oauthTokenProvider: NativeOAuthTokenProvider = UnconfiguredNativeOAuthTokenProvider(),
    private val uploadProvider: NativeUploadProvider = UnconfiguredNativeUploadProvider(),
    private val externalLinkOpener: NativeExternalLinkOpener = UnconfiguredNativeExternalLinkOpener(),
) : ViewModel() {
    private val _state = MutableStateFlow(ThoughtPinsUiState())

    fun supportsOAuth(provider: ThoughtPinsOAuthProvider): Boolean = oauthTokenProvider.supports(provider)
    val state: StateFlow<ThoughtPinsUiState> = _state

    fun bootstrap() = viewModelScope.launch {
        runCatching { api.clientConfig() }
            .onSuccess { config ->
                _state.update {
                    it.copy(clientConfig = config, maintenanceMessage = if (config.maintenanceMode) config.maintenanceMessage ?: "Maintenance currently in progress." else null)
                }
            }
            .onFailure { _state.update { it.copy(banner = "Could not reach Thought Pins. You can keep drafting locally.") } }
        val loadedMe = runCatching { api.me() }.getOrNull()
        loadedMe?.let { me -> _state.update { it.copy(me = me) } }
        if (loadedMe != null) refreshPreferences()
        if (loadedMe != null) syncDrafts(silent = true)
        refreshReadModels()
        refreshDraftCount()
    }

    fun register(email: String?, phone: String?, password: String, consentToAIProcessing: Boolean) = viewModelScope.launch {
        if (!consentToAIProcessing) {
            _state.update { it.copy(banner = "Review and accept the privacy, terms, and AI processing disclosure to create an account.") }
            return@launch
        }
        runCatching {
            api.register(email = email, phone = phone, password = password)
            val identifier = listOfNotNull(email, phone).firstOrNull { it.isNotBlank() }
                ?: error("Add an email address or phone number.")
            api.login(identifier, password)
            val me = api.me()
            val version = _state.value.clientConfig?.legalDocumentVersion ?: "2026-07-13"
            api.acceptLegalDocument("privacy", version)
            api.acceptLegalDocument("terms", version)
            api.acceptLegalDocument("ai_disclosure", version)
            me
        }
            .onSuccess { me ->
                _state.update { it.copy(me = me, banner = "Account created.") }
                refreshPreferences()
                refreshReadModels()
            }
            .onFailure { _state.update { it.copy(banner = "Registration failed.") } }
    }

    fun login(identifier: String, password: String) = viewModelScope.launch {
        runCatching {
            api.login(identifier, password)
            api.me()
        }
            .onSuccess { me ->
                _state.update { it.copy(me = me, banner = "Signed in.") }
                refreshPreferences()
                refreshReadModels()
            }
            .onFailure { _state.update { it.copy(banner = "Sign in failed.") } }
    }

    fun oauthLogin(provider: ThoughtPinsOAuthProvider) = viewModelScope.launch {
        runCatching {
            val credential = oauthTokenProvider.credential(provider)
            api.oauthLogin(
                provider = provider.wireName,
                idToken = credential.idToken,
                displayName = credential.displayName,
                nonce = credential.nonce,
            )
            api.me()
        }
            .onSuccess { me ->
                _state.update { it.copy(me = me, banner = "Signed in with ${provider.label}.") }
                refreshPreferences()
                refreshReadModels()
            }
            .onFailure { error -> _state.update { it.copy(banner = error.message ?: "${provider.label} is not configured.") } }
    }

    fun sendChat(text: String) = viewModelScope.launch {
        if (text.isBlank()) return@launch
        if (!_state.value.aiProcessingConsentAccepted) {
            _state.update { it.copy(banner = "Allow AI processing before sending personal content.") }
            return@launch
        }
        _state.value.maintenanceMessage?.let { message ->
            _state.update { current -> current.copy(banner = message) }
            return@launch
        }
        _state.update { it.copy(isThinking = true) }
        try {
            val response = api.chat(
                text = text,
                surface = "android",
                includePrivate = _state.value.usePrivateMemories,
            )
            _state.update { it.copy(chatReply = response.reply, routeLabel = response.routeType) }
            runCatching { refreshReadModels() }
        } catch (_: Exception) {
            _state.update { it.copy(banner = "Chat failed. Your account data is still safe.") }
        } finally {
            _state.update { it.copy(isThinking = false) }
        }
    }

    fun updateResponseStyle(style: String) = viewModelScope.launch {
        if (style !in setOf("friendly", "clear", "mirror")) return@launch
        runCatching { api.updatePreferences(PreferencesUpdateRequest(responseStyle = style)) }
            .onSuccess { preferences -> _state.update { it.copy(responseStyle = preferences.responseStyle, banner = "Response voice updated.") } }
            .onFailure { _state.update { it.copy(banner = "Could not update the response voice.") } }
    }

    fun updateEntryImportance(entryId: String, value: Int?) = viewModelScope.launch {
        runCatching { api.updateEntryImportance(entryId, value) }
            .onSuccess { updated ->
                _state.update { current ->
                    current.copy(
                        recentEntries = current.recentEntries.map { if (it.id == entryId) updated else it },
                        banner = value?.let { "Importance set to $it of 5." } ?: "Importance cleared.",
                    )
                }
            }
            .onFailure { _state.update { it.copy(banner = "Could not update importance.") } }
    }

    fun updateImportancePrompts(enabled: Boolean) = viewModelScope.launch {
        runCatching { api.updatePreferences(PreferencesUpdateRequest(importancePromptsEnabled = enabled)) }
            .onSuccess { preferences ->
                _state.update {
                    it.copy(
                        importancePromptsEnabled = preferences.importancePromptsEnabled,
                        banner = if (enabled) "Importance prompts enabled." else "Importance prompts disabled.",
                    )
                }
            }
            .onFailure { _state.update { it.copy(banner = "Could not update importance prompts.") } }
    }

    fun saveJournal(text: String) = viewModelScope.launch {
        if (text.isBlank()) return@launch
        if (!_state.value.aiProcessingConsentAccepted) {
            _state.update { it.copy(banner = "Allow AI processing before saving journal content.") }
            return@launch
        }
        runCatching { api.ingest(text) }
            .onSuccess { response ->
                _state.update { it.copy(banner = if (response.jobId == null) "Journal saved." else "Journal queued for memory extraction.") }
                refreshReadModels()
            }
            .onFailure {
                runCatching { draftQueue.enqueue(text) }
                refreshDraftCount()
                _state.update { it.copy(banner = "Saved as an encrypted offline draft.") }
            }
    }

    fun ingestLink(url: String) = viewModelScope.launch {
        if (url.isBlank()) return@launch
        if (!_state.value.aiProcessingConsentAccepted) {
            _state.update { it.copy(banner = "Allow AI processing before adding a reading.") }
            return@launch
        }
        runCatching { api.createLibrarySource(url = url, sourceType = "article") }
            .onSuccess {
                _state.update { it.copy(banner = "Reading saved.") }
                refreshReadModels()
            }
            .onFailure { _state.update { it.copy(banner = "Could not import that link.") } }
    }

    fun uploadSelectedFile(destination: NativeUploadDestination = NativeUploadDestination.AUTO) = viewModelScope.launch {
        if (!_state.value.aiProcessingConsentAccepted) {
            _state.update { it.copy(banner = "Allow AI processing before uploading personal content.") }
            return@launch
        }
        val payload = runCatching { uploadProvider.payload(destination) }.getOrElse { error ->
            _state.update { it.copy(banner = error.message ?: "Upload failed.") }
            return@launch
        }
        if (destination == NativeUploadDestination.OBSIDIAN_VAULT) {
            runCatching {
                api.previewObsidianVaultResumable(payload.filename, payload.contentBase64)
            }
                .onSuccess { preview ->
                    val result = preview.result
                    _state.update {
                        it.copy(
                            pendingVaultImport = preview,
                            banner = "Vault preview ready: ${result?.newNotes ?: 0} new, ${result?.changedNotes ?: 0} changed.",
                        )
                    }
                }
                .onFailure { error -> _state.update { it.copy(banner = error.message ?: "Vault import failed.") } }
            return@launch
        }
        runCatching {
            api.uploadFile(
                filename = payload.filename,
                contentBase64 = payload.contentBase64,
                mediaType = payload.mediaType,
                destination = destination.wireName,
                caption = payload.caption,
                title = payload.title,
                sourceType = payload.sourceType,
                conversationId = "native-upload",
            )
        }
            .onSuccess { response ->
                val message = when {
                    response.documentId != null -> "Upload saved to your library."
                    response.entryId != null -> "Upload saved as a journal entry."
                    else -> "Upload processed: ${response.extractionStatus}."
                }
                _state.update { it.copy(banner = message) }
                refreshReadModels()
            }
            .onFailure { error -> _state.update { it.copy(banner = error.message ?: "Upload failed.") } }
    }

    fun applyPendingVaultImport() = viewModelScope.launch {
        val pending = _state.value.pendingVaultImport ?: return@launch
        runCatching { api.applyPreviewedVaultImport(pending.id, pending.conflictPolicy) }
            .onSuccess { response ->
                _state.update {
                    it.copy(
                        pendingVaultImport = null,
                        banner = "Vault imported: ${response.imported} notes; ${response.journalJobsQueued} queued.",
                    )
                }
                refreshReadModels()
            }
            .onFailure { error -> _state.update { it.copy(banner = error.message ?: "Vault import failed.") } }
    }

    fun discardPendingVaultImport() = viewModelScope.launch {
        val pending = _state.value.pendingVaultImport ?: return@launch
        runCatching { api.cancelVaultImport(pending.id) }
            .onSuccess { _state.update { it.copy(pendingVaultImport = null, banner = "Vault preview discarded.") } }
            .onFailure { error -> _state.update { it.copy(banner = error.message ?: "Could not discard the preview.") } }
    }

    fun uploadVoiceNote(bytes: ByteArray) = viewModelScope.launch {
        if (!_state.value.aiProcessingConsentAccepted) {
            _state.update { it.copy(banner = "Allow AI processing before uploading a voice note.") }
            return@launch
        }
        if (bytes.isEmpty()) {
            _state.update { it.copy(banner = "The voice note was empty.") }
            return@launch
        }
        runCatching {
            api.uploadFile(
                filename = "voice-note-${System.currentTimeMillis()}.m4a",
                contentBase64 = Base64.encodeToString(bytes, Base64.NO_WRAP),
                mediaType = "audio/mp4",
                destination = NativeUploadDestination.JOURNAL.wireName,
                caption = "Voice note",
                title = "Voice note",
                sourceType = "voice_note",
                conversationId = "android-voice",
            )
        }.onSuccess { response ->
            val message = when {
                response.entryId == null -> response.error ?: "No speech was recognized in that voice note."
                response.voiceAssetId != null -> "Voice note saved with its encrypted recording."
                else -> "Voice note saved. The recording was discarded after transcription."
            }
            _state.update { it.copy(banner = message) }
            refreshReadModels()
        }.onFailure {
            _state.update { it.copy(banner = "Voice note failed. Your local draft remains safe.") }
        }
    }

    fun openLegalLink(label: String, url: String) = viewModelScope.launch {
        runCatching { externalLinkOpener.open(url) }
            .onSuccess { _state.update { it.copy(banner = "Opened $label.") } }
            .onFailure { error -> _state.update { it.copy(banner = error.message ?: "Could not open $label.") } }
    }

    fun acceptLegal(document: String) = viewModelScope.launch {
        val version = _state.value.clientConfig?.legalDocumentVersion ?: "2026-07-13"
        runCatching { api.acceptLegalDocument(document, version) }
            .onSuccess { preferences ->
                _state.update {
                    it.copy(
                        aiProcessingConsentAccepted = preferences.legalAcceptances.containsKey("ai_disclosure"),
                        banner = if (document == "ai_disclosure") "AI processing permission saved." else "Legal acknowledgement saved.",
                    )
                }
            }
            .onFailure { _state.update { it.copy(banner = "Could not save legal acknowledgement.") } }
    }

    fun exportAccount() = viewModelScope.launch {
        runCatching { api.exportAccount() }
            .onSuccess { export -> _state.update { it.copy(banner = "Export ready with ${export.tables.size} data groups.") } }
            .onFailure { _state.update { it.copy(banner = "Export failed.") } }
    }

    fun setUsePrivateMemories(enabled: Boolean) {
        _state.update { it.copy(usePrivateMemories = enabled) }
    }

    fun updatePrivateRecallDefault(enabled: Boolean) = viewModelScope.launch {
        runCatching { api.updatePreferences(PreferencesUpdateRequest(privateEntriesInAsk = enabled)) }
            .onSuccess { preferences ->
                _state.update {
                    it.copy(
                        usePrivateMemories = preferences.privateEntriesInAsk,
                        banner = if (enabled) {
                            "Private memories may inform replies."
                        } else {
                            "Private memories stay out of replies."
                        },
                    )
                }
            }
            .onFailure { _state.update { it.copy(banner = "Could not update private-memory recall.") } }
    }

    fun enableVoiceArchive() = viewModelScope.launch {
        val consent = com.thoughtpins.core.VoiceArchiveConsentRequest(
            retainRecordings = true,
            acknowledgeSensitiveAudio = true,
            acknowledgePersonalUseOnly = true,
            acknowledgeDeletionAvailable = true,
        )
        runCatching { api.enableVoiceArchive(consent) }
            .onSuccess { next -> _state.update { it.copy(voiceArchiveStatus = next, banner = "Personal voice archive enabled.") } }
            .onFailure { _state.update { it.copy(banner = "Could not enable the voice archive.") } }
    }

    fun disableVoiceArchive() = viewModelScope.launch {
        runCatching { api.disableVoiceArchive() }
            .onSuccess { next -> _state.update { it.copy(voiceArchiveStatus = next, banner = "Future voice retention disabled.") } }
            .onFailure { _state.update { it.copy(banner = "Could not update voice retention.") } }
    }

    fun deleteVoiceArchive() = viewModelScope.launch {
        runCatching { api.deleteVoiceArchive() }
            .onSuccess {
                val next = runCatching { api.voiceArchive() }.getOrNull()
                _state.update { it.copy(voiceArchiveStatus = next, banner = "Retained voice recordings deleted.") }
            }
            .onFailure { _state.update { it.copy(banner = "Could not delete the voice archive.") } }
    }

    fun deleteAccount() = viewModelScope.launch {
        runCatching { api.deleteAccount() }
            .onSuccess {
                clearLocalAccountData()
                _state.update { ThoughtPinsUiState(banner = "Account deleted.") }
            }
            .onFailure { _state.update { it.copy(banner = "Deletion failed.") } }
    }

    fun logout() = viewModelScope.launch {
        runCatching { api.logout() }
        clearLocalAccountData()
        _state.update { ThoughtPinsUiState(banner = "Signed out.") }
    }

    /**
     * Takes the departing account's offline drafts with it.
     *
     * Resetting [ThoughtPinsUiState] clears the screen but not the disk. The
     * draft queue is keyed by device, and bootstrap syncs it under whichever
     * session is live, so drafts left behind by one account are posted into the
     * next account that signs in here.
     */
    private suspend fun clearLocalAccountData() {
        runCatching { draftQueue.purge() }
    }

    fun syncDrafts(silent: Boolean = false) = viewModelScope.launch {
        val summary = runCatching { api.syncQueuedDrafts(draftQueue) }.getOrNull()
        refreshDraftCount()
        if (!silent && summary != null) {
            _state.update { it.copy(banner = "Synced ${summary.synced} of ${summary.attempted} drafts.") }
        } else if (!silent && summary == null) {
            _state.update { it.copy(banner = "Draft sync failed. Try again when online.") }
        }
    }

    fun clearBanner() {
        _state.update { it.copy(banner = null) }
    }

    private suspend fun refreshPreferences() {
        val preferences = runCatching { api.preferences() }.getOrNull() ?: return
        val voiceArchive = if (_state.value.clientConfig?.voiceArchiveEnabled == true) {
            runCatching { api.voiceArchive() }.getOrNull()
        } else {
            null
        }
        _state.update {
            it.copy(
                responseStyle = preferences.responseStyle,
                importancePromptsEnabled = preferences.importancePromptsEnabled,
                usePrivateMemories = preferences.privateEntriesInAsk,
                aiProcessingConsentAccepted = preferences.legalAcceptances.containsKey("ai_disclosure"),
                voiceArchiveStatus = voiceArchive,
            )
        }
    }

    private suspend fun refreshReadModels() {
        val library = runCatching { api.librarySources(limit = 20) }.getOrDefault(_state.value.librarySources)
        val cards = runCatching { api.memoryCards(section = "people", limit = 12).items }.getOrDefault(_state.value.memoryCards)
        val places = runCatching { api.memoryCards(section = "places", limit = 12).items }.getOrDefault(_state.value.placeCards)
        val entries = runCatching { api.entries(page = 1, limit = 40).items }.getOrDefault(_state.value.recentEntries)
        _state.update { it.copy(librarySources = library, memoryCards = cards, placeCards = places, recentEntries = entries) }
    }

    private suspend fun refreshDraftCount() {
        val count = runCatching { draftQueue.pending().size }.getOrDefault(0)
        _state.update { it.copy(draftCount = count) }
    }
}
