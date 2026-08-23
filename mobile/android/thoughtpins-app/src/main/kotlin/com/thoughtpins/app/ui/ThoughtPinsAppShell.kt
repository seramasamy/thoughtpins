package com.thoughtpins.app.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import com.thoughtpins.core.DraftQueue
import com.thoughtpins.core.ThoughtPinsApiClient


@Composable
fun ThoughtPinsApp(
    api: ThoughtPinsApiClient,
    draftQueue: DraftQueue,
    oauthTokenProvider: NativeOAuthTokenProvider = UnconfiguredNativeOAuthTokenProvider(),
    uploadProvider: NativeUploadProvider = UnconfiguredNativeUploadProvider(),
    voiceRecorder: NativeVoiceRecorder = UnconfiguredNativeVoiceRecorder(),
    externalLinkOpener: NativeExternalLinkOpener = UnconfiguredNativeExternalLinkOpener(),
    viewModel: ThoughtPinsViewModel = remember(api, draftQueue, oauthTokenProvider, uploadProvider, externalLinkOpener) {
        ThoughtPinsViewModel(api, draftQueue, oauthTokenProvider, uploadProvider, externalLinkOpener)
    },
) {
    val state by viewModel.state.collectAsState()
    LaunchedEffect(Unit) { viewModel.bootstrap() }
    val darkTheme = isSystemInDarkTheme()
    MaterialTheme(
        colorScheme = if (darkTheme) ThoughtPinsDarkColorScheme else ThoughtPinsLightColorScheme,
        typography = ThoughtPinsTypography,
        shapes = ThoughtPinsShapes,
    ) {
        Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
            when {
                state.me == null -> ThoughtPinsAuthScreen(state, viewModel)
                !state.aiProcessingConsentAccepted -> ThoughtPinsAIConsentScreen(state, viewModel)
                // After consent, so the account is fully created and its details
                // kept before the wall appears — the same order the web app uses.
                // The null check matters: the gate is unknown until asked, and
                // defaulting to "blocked" would flash this screen at an admitted
                // account on every cold start.
                state.inviteStatus?.let { it.inviteRequired && !it.admitted } == true ->
                    ThoughtPinsInviteScreen(state, viewModel)
                else -> ThoughtPinsMainShell(state, viewModel, voiceRecorder)
            }
        }
    }
}
