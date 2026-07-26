package com.thoughtpins.app.ui

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

enum class ThoughtPinsOAuthProvider(val wireName: String, val label: String) {
    APPLE("apple", "Sign in with Apple"),
    GOOGLE("google", "Sign in with Google"),
}

data class NativeOAuthCredential(
    val idToken: String,
    val displayName: String? = null,
    val nonce: String? = null,
)

interface NativeOAuthTokenProvider {
    fun supports(provider: ThoughtPinsOAuthProvider): Boolean
    suspend fun credential(provider: ThoughtPinsOAuthProvider): NativeOAuthCredential
}

class UnconfiguredNativeOAuthTokenProvider : NativeOAuthTokenProvider {
    override fun supports(provider: ThoughtPinsOAuthProvider): Boolean = false

    override suspend fun credential(provider: ThoughtPinsOAuthProvider): NativeOAuthCredential =
        error("${provider.label} is not configured in this build.")
}

enum class NativeUploadDestination(val wireName: String, val label: String) {
    AUTO("auto", "Auto"),
    LIBRARY("library", "Library"),
    JOURNAL("journal", "Journal"),
    OBSIDIAN_VAULT("obsidian_vault", "Obsidian Vault"),
}

data class NativeUploadPayload(
    val filename: String,
    val contentBase64: String,
    val mediaType: String? = null,
    val caption: String? = null,
    val title: String? = null,
    val sourceType: String? = null,
)

interface NativeUploadProvider {
    suspend fun payload(destination: NativeUploadDestination): NativeUploadPayload
}

class UnconfiguredNativeUploadProvider : NativeUploadProvider {
    override suspend fun payload(destination: NativeUploadDestination): NativeUploadPayload =
        error("Native file selection is not configured for ${destination.label} uploads in this build.")
}

interface NativeVoiceRecorder {
    val isRecording: StateFlow<Boolean>
    val errorMessage: StateFlow<String?>
    fun start()
    fun stop(): ByteArray?
    fun cancel()
}

class UnconfiguredNativeVoiceRecorder : NativeVoiceRecorder {
    override val isRecording = MutableStateFlow(false)
    override val errorMessage = MutableStateFlow<String?>("Voice recording is not configured in this build.")
    override fun start() = Unit
    override fun stop(): ByteArray? = null
    override fun cancel() = Unit
}

interface NativeExternalLinkOpener {
    suspend fun open(url: String)
}

class UnconfiguredNativeExternalLinkOpener : NativeExternalLinkOpener {
    override suspend fun open(url: String) {
        error("Native external link opening is not configured for $url.")
    }
}

internal fun legalUrl(configured: String?, fallbackPath: String): String {
    if (!configured.isNullOrBlank()) {
        return if (configured.startsWith("/")) "https://thoughtpins.com$configured" else configured
    }
    return "https://thoughtpins.com$fallbackPath"
}
