package com.thoughtpins.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp


@Composable
internal fun ThoughtPinsAccountScreen(state: ThoughtPinsUiState, viewModel: ThoughtPinsViewModel) {
    var showingDeleteConfirmation by rememberSaveable { mutableStateOf(false) }
    var showingVoiceConsent by rememberSaveable { mutableStateOf(false) }
    var showingVoiceDeleteConfirmation by rememberSaveable { mutableStateOf(false) }
    val privacyUrl = legalUrl(state.clientConfig?.privacyPolicyUrl, "/privacy")
    val termsUrl = legalUrl(state.clientConfig?.termsUrl, "/terms")
    val supportUrl = legalUrl(state.clientConfig?.supportUrl, "/support")
    val deletionUrl = legalUrl(state.clientConfig?.accountDeletionUrl, "/account/delete")
    val aiDisclosureUrl = legalUrl(state.clientConfig?.aiDisclosureUrl, "/ai-disclosure")
    Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(state.me?.email ?: state.me?.phone ?: "Thought Pins account", style = MaterialTheme.typography.titleMedium)
        Text("Response voice", style = MaterialTheme.typography.titleSmall)
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            listOf(
                "friendly" to "Friendly & professional",
                "clear" to "Clear & concise",
                "mirror" to "Match my style",
            ).forEach { (id, label) ->
                FilterChip(
                    selected = state.responseStyle == id,
                    onClick = { viewModel.updateResponseStyle(id) },
                    label = { Text(label) },
                )
            }
        }
        Text(
            "Friendly & professional is the default. Matching your style is always an explicit choice.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Row(verticalAlignment = Alignment.CenterVertically) {
            Checkbox(
                checked = state.importancePromptsEnabled,
                onCheckedChange = { viewModel.updateImportancePrompts(it) },
            )
            Text("Occasional importance prompts")
        }
        Text(
            "Prompts are optional and only appear after substantial saves.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text("Private recall", style = MaterialTheme.typography.titleSmall)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Checkbox(
                checked = state.usePrivateMemories,
                onCheckedChange = viewModel::updatePrivateRecallDefault,
            )
            Text("Use private memories in replies by default")
        }
        Text(
            "Off by default. Private memories stay out of recall unless you explicitly enable them. This setting does not mark new messages private.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (state.clientConfig?.voiceArchiveEnabled == true) {
            Text("Personal voice archive", style = MaterialTheme.typography.titleSmall)
            state.voiceArchiveStatus?.let { status ->
            Text(
                if (status.enabled) "On - ${status.assetCount} recordings (${formatVoiceBytes(status.originalBytes)})" else "Off - ${status.assetCount} retained recordings",
                style = MaterialTheme.typography.bodyMedium,
            )
            Text(
                "Voice notes are transcribed and discarded by default. The archive retains encrypted recordings only for future features built for your account.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (status.enabled) {
                TextButton(onClick = viewModel::disableVoiceArchive) { Text("Stop future retention") }
            } else {
                Button(onClick = { showingVoiceConsent = true }, modifier = Modifier.heightIn(min = 48.dp)) {
                    Text("Review and enable")
                }
            }
            if (status.assetCount > 0) {
                TextButton(onClick = { showingVoiceDeleteConfirmation = true }) {
                    Text("Delete retained recordings", color = MaterialTheme.colorScheme.error)
                }
            }
            } ?: Text("Loading voice archive", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Text("Legal and support", style = MaterialTheme.typography.titleSmall)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            TextButton(onClick = { viewModel.openLegalLink("Privacy Policy", privacyUrl) }) { Text("Privacy Policy") }
            TextButton(onClick = { viewModel.openLegalLink("Terms", termsUrl) }) { Text("Terms") }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            TextButton(onClick = { viewModel.openLegalLink("Support", supportUrl) }) { Text("Support") }
            TextButton(onClick = { viewModel.openLegalLink("Account Deletion", deletionUrl) }) {
                Text("Account Deletion")
            }
        }
        TextButton(onClick = { viewModel.openLegalLink("AI Disclosure", aiDisclosureUrl) }) {
            Text("AI Disclosure")
        }
        Text(
            if (state.aiProcessingConsentAccepted) {
                "AI processing permission is active."
            } else {
                "AI processing permission is not active."
            },
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Button(onClick = { viewModel.exportAccount() }, modifier = Modifier.heightIn(min = 48.dp)) {
            Text("Export account")
        }
        TextButton(onClick = { showingDeleteConfirmation = true }, modifier = Modifier.heightIn(min = 48.dp)) {
            Text("Delete account", color = MaterialTheme.colorScheme.error)
        }
        TextButton(onClick = { viewModel.logout() }) { Text("Sign out") }
    }
    if (showingDeleteConfirmation) {
        AlertDialog(
            onDismissRequest = { showingDeleteConfirmation = false },
            title = { Text("Delete your account?") },
            text = {
                Text(
                    "This permanently removes your Thought Pins account and saved data. " +
                        "Export anything you want to keep first.",
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        showingDeleteConfirmation = false
                        viewModel.deleteAccount()
                    },
                ) { Text("Delete", color = MaterialTheme.colorScheme.error) }
            },
            dismissButton = {
                TextButton(onClick = { showingDeleteConfirmation = false }) { Text("Cancel") }
            },
        )
    }
    if (showingVoiceConsent) {
        VoiceArchiveConsentDialog(
            onDismiss = { showingVoiceConsent = false },
            onConfirm = {
                showingVoiceConsent = false
                viewModel.enableVoiceArchive()
            },
        )
    }
    if (showingVoiceDeleteConfirmation) {
        AlertDialog(
            onDismissRequest = { showingVoiceDeleteConfirmation = false },
            title = { Text("Delete retained recordings?") },
            text = { Text("Encrypted audio and future derived voice data are removed. Journal transcripts remain until you delete their entries or your account.") },
            confirmButton = {
                TextButton(onClick = {
                    showingVoiceDeleteConfirmation = false
                    viewModel.deleteVoiceArchive()
                }) { Text("Delete archive", color = MaterialTheme.colorScheme.error) }
            },
            dismissButton = { TextButton(onClick = { showingVoiceDeleteConfirmation = false }) { Text("Cancel") } },
        )
    }
}

@Composable
private fun VoiceArchiveConsentDialog(onDismiss: () -> Unit, onConfirm: () -> Unit) {
    var retainRecordings by rememberSaveable { mutableStateOf(false) }
    var sensitiveAudio by rememberSaveable { mutableStateOf(false) }
    var personalUseOnly by rememberSaveable { mutableStateOf(false) }
    var deletionAvailable by rememberSaveable { mutableStateOf(false) }
    val confirmed = retainRecordings && sensitiveAudio && personalUseOnly && deletionAvailable
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Personal voice archive") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Voice recordings can identify you. Thought Pins retains them only for features built for your account, never for a shared model or another user's model.")
                ConsentRow("Retain future recordings after transcription", retainRecordings) { retainRecordings = it }
                ConsentRow("I understand voice audio is sensitive and identifying", sensitiveAudio) { sensitiveAudio = it }
                ConsentRow("Use recordings only for my personal voice features", personalUseOnly) { personalUseOnly = it }
                ConsentRow("I can disable retention or delete the archive at any time", deletionAvailable) { deletionAvailable = it }
            }
        },
        confirmButton = { TextButton(onClick = onConfirm, enabled = confirmed) { Text("Enable") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
private fun ConsentRow(label: String, checked: Boolean, onCheckedChange: (Boolean) -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Checkbox(checked = checked, onCheckedChange = onCheckedChange)
        Text(label, style = MaterialTheme.typography.bodySmall)
    }
}

private fun formatVoiceBytes(bytes: Long): String = when {
    bytes < 1_024 -> "$bytes B"
    bytes < 1_048_576 -> "%.1f KB".format(bytes / 1_024.0)
    else -> "%.1f MB".format(bytes / 1_048_576.0)
}
