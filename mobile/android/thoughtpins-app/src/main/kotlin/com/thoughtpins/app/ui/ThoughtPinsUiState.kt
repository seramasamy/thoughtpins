package com.thoughtpins.app.ui

import com.thoughtpins.core.ClientConfig
import com.thoughtpins.core.EntryResponse
import com.thoughtpins.core.LibrarySourceResponse
import com.thoughtpins.core.MeResponse
import com.thoughtpins.core.MemoryCardResponse
import com.thoughtpins.core.VaultImportSessionResponse
import com.thoughtpins.core.VoiceArchiveStatusResponse

data class ThoughtPinsUiState(
    val me: MeResponse? = null,
    val clientConfig: ClientConfig? = null,
    val maintenanceMessage: String? = null,
    val banner: String? = null,
    val chatReply: String = "",
    val routeLabel: String = "chat",
    val isThinking: Boolean = false,
    val responseStyle: String = "friendly",
    val importancePromptsEnabled: Boolean = false,
    val usePrivateMemories: Boolean = false,
    val aiProcessingConsentAccepted: Boolean = false,
    val voiceArchiveStatus: VoiceArchiveStatusResponse? = null,
    val librarySources: List<LibrarySourceResponse> = emptyList(),
    val memoryCards: List<MemoryCardResponse> = emptyList(),
    val placeCards: List<MemoryCardResponse> = emptyList(),
    val recentEntries: List<EntryResponse> = emptyList(),
    val pendingVaultImport: VaultImportSessionResponse? = null,
    val draftCount: Int = 0,
)
