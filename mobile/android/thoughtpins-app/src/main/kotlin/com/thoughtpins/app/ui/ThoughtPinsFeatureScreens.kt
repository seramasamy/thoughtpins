package com.thoughtpins.app.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
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
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.outlined.Star
import androidx.compose.material3.Button
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.thoughtpins.core.LibrarySourceResponse
import com.thoughtpins.core.MemoryCardResponse
import kotlinx.coroutines.delay


@Composable
internal fun ThoughtPinsRecapScreen(state: ThoughtPinsUiState, viewModel: ThoughtPinsViewModel) {
    var period by rememberSaveable { mutableStateOf("Day") }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("Day", "Week", "Month").forEach { item ->
                if (period == item) Button(onClick = { period = item }) { Text(item) }
                else TextButton(onClick = { period = item }) { Text(item) }
            }
        }
        if (state.recentEntries.isEmpty()) {
            ThoughtPinsEmptyState(
                title = "Nothing here yet",
                message = "Your journal entries will gather here as you capture them.",
            )
        } else {
            LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(state.recentEntries, key = { it.id }) { entry ->
                    Card(Modifier.fillMaxWidth().animateItem()) {
                        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                            Text(
                                entry.localDate ?: entry.createdAtUtc,
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.primary,
                            )
                            Text(entry.rawText, style = MaterialTheme.typography.bodyMedium)
                            Text(
                                "Importance",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                                (1..5).forEach { rating ->
                                    IconButton(onClick = { viewModel.updateEntryImportance(entry.id, rating) }) {
                                        Icon(
                                            imageVector = if (rating <= (entry.userImportance ?: 0)) {
                                                Icons.Filled.Star
                                            } else {
                                                Icons.Outlined.Star
                                            },
                                            contentDescription = "Set importance to $rating out of 5",
                                            tint = if (rating <= (entry.userImportance ?: 0)) {
                                                TerracottaBrand
                                            } else {
                                                MaterialTheme.colorScheme.onSurfaceVariant
                                            },
                                        )
                                    }
                                }
                            }
                            if (entry.userImportance != null) {
                                TextButton(onClick = { viewModel.updateEntryImportance(entry.id, null) }) {
                                    Text("Clear rating")
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}


@Composable
internal fun ThoughtPinsChatScreen(
    state: ThoughtPinsUiState,
    viewModel: ThoughtPinsViewModel,
    voiceRecorder: NativeVoiceRecorder,
) {
    var text by rememberSaveable { mutableStateOf("") }
    var voiceDisclosureAccepted by rememberSaveable { mutableStateOf(false) }
    var showingVoiceDisclosure by rememberSaveable { mutableStateOf(false) }
    val isRecording by voiceRecorder.isRecording.collectAsState()
    val voiceError by voiceRecorder.errorMessage.collectAsState()
    val submit = {
        val payload = text.trim()
        if (payload.isNotEmpty() && !state.isThinking) {
            text = ""
            viewModel.sendChat(payload)
        }
    }
    LaunchedEffect(isRecording) {
        if (isRecording) {
            delay(10 * 60 * 1000L)
            if (voiceRecorder.isRecording.value) {
                voiceRecorder.stop()?.let(viewModel::uploadVoiceNote)
            }
        }
    }
    DisposableEffect(voiceRecorder) {
        onDispose { voiceRecorder.cancel() }
    }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Checkbox(
                checked = state.usePrivateMemories,
                onCheckedChange = viewModel::setUsePrivateMemories,
            )
            Text("Use private memories")
        }
        Text(
            if (state.usePrivateMemories) {
                "Private memories may inform this reply."
            } else {
                "Private memories stay out of replies."
            },
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (state.chatReply.isBlank()) {
            ThoughtPinsEmptyState(
                title = "Ask Thought Pins anything",
                message = "Notes, links, reminders, searches, and questions route automatically.",
            )
        } else {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (state.routeLabel.isNotBlank()) {
                    Surface(
                        color = MaterialTheme.colorScheme.secondaryContainer,
                        contentColor = MaterialTheme.colorScheme.onSecondaryContainer,
                        shape = CircleShape,
                    ) {
                        Text(
                            state.routeLabel.replaceFirstChar { it.uppercaseChar() },
                            style = MaterialTheme.typography.labelSmall,
                            modifier = Modifier.padding(horizontal = 9.dp, vertical = 3.dp),
                        )
                    }
                }
                Surface(
                    color = MaterialTheme.colorScheme.surface,
                    shape = RoundedCornerShape(4.dp, 14.dp, 14.dp, 14.dp),
                    border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
                ) {
                    Text(
                        state.chatReply,
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.padding(horizontal = 14.dp, vertical = 11.dp),
                    )
                }
            }
        }
        val animationsEnabled = rememberAnimationsEnabled()
        val thinkingDuration = if (animationsEnabled) 220 else 0
        AnimatedVisibility(
            visible = state.isThinking,
            enter = fadeIn(tween(thinkingDuration)) + expandVertically(tween(thinkingDuration)),
            exit = fadeOut(tween(thinkingDuration)) + shrinkVertically(tween(thinkingDuration)),
        ) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                ThinkingDots()
                Text(
                    "Thinking with your memory",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
                )
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(
                onClick = {
                    if (isRecording) {
                        voiceRecorder.stop()?.let(viewModel::uploadVoiceNote)
                    } else {
                        if (voiceDisclosureAccepted) voiceRecorder.start() else showingVoiceDisclosure = true
                    }
                },
                enabled = !state.isThinking,
                modifier = Modifier.size(48.dp),
            ) {
                val micAlpha = if (isRecording && animationsEnabled) {
                    val pulse = rememberInfiniteTransition(label = "mic-pulse")
                    val alpha by pulse.animateFloat(
                        initialValue = 0.5f,
                        targetValue = 1f,
                        animationSpec = infiniteRepeatable(tween(600), RepeatMode.Reverse),
                        label = "mic-alpha",
                    )
                    alpha
                } else {
                    1f
                }
                Icon(
                    imageVector = if (isRecording) Icons.Filled.Stop else Icons.Filled.Mic,
                    contentDescription = if (isRecording) "Stop voice note" else "Record a voice note",
                    tint = (if (isRecording) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary).copy(alpha = micAlpha),
                )
            }
            OutlinedTextField(
                value = text,
                onValueChange = { text = it },
                label = { Text("Ask your memory") },
                modifier = Modifier.weight(1f),
                enabled = !state.isThinking,
                minLines = 1,
                maxLines = 4,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                keyboardActions = KeyboardActions(onSend = { submit() }),
            )
        }
        if (isRecording) {
            Text(
                "Recording voice note",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        voiceError?.let {
            Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Button(
            onClick = submit,
            enabled = text.isNotBlank() && !state.isThinking,
            modifier = Modifier.heightIn(min = 48.dp),
        ) { Text("Send") }
    }
    if (showingVoiceDisclosure) {
        AlertDialog(
            onDismissRequest = { showingVoiceDisclosure = false },
            title = { Text("Record a voice note") },
            text = {
                Text(
                    if (state.clientConfig?.voiceArchiveEnabled == true) {
                        "Thought Pins sends this recording for transcription. Audio is discarded after processing unless you separately enable Personal voice archive in Account."
                    } else {
                        "Thought Pins sends this recording for transcription and discards the audio after processing. The transcript is saved as a journal entry."
                    },
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    voiceDisclosureAccepted = true
                    showingVoiceDisclosure = false
                    voiceRecorder.start()
                }) { Text("Continue") }
            },
            dismissButton = { TextButton(onClick = { showingVoiceDisclosure = false }) { Text("Cancel") } },
        )
    }
}


@Composable
internal fun ThoughtPinsCaptureScreen(state: ThoughtPinsUiState, viewModel: ThoughtPinsViewModel) {
    var journal by rememberSaveable { mutableStateOf("") }
    var link by rememberSaveable { mutableStateOf("") }
    var uploadDestination by remember { mutableStateOf(NativeUploadDestination.AUTO) }
    Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        OutlinedTextField(
            journal,
            { journal = it },
            label = { Text("Journal note") },
            modifier = Modifier.fillMaxWidth(),
            minLines = 5,
        )
        Button(
            onClick = {
                val payload = journal
                journal = ""
                viewModel.saveJournal(payload)
            },
            modifier = Modifier.heightIn(min = 48.dp),
        ) { Text("Save journal") }
        OutlinedTextField(
            link,
            { link = it },
            label = { Text("Article or document link") },
            modifier = Modifier.fillMaxWidth(),
        )
        Button(
            onClick = {
                val payload = link
                link = ""
                viewModel.ingestLink(payload)
            },
            modifier = Modifier.heightIn(min = 48.dp),
        ) { Text("Import link") }
        Text("Upload or share a selected file", style = MaterialTheme.typography.titleSmall)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(
                onClick = {
                    uploadDestination = NativeUploadDestination.AUTO
                    viewModel.uploadSelectedFile(uploadDestination)
                },
            ) { Text("Auto") }
            TextButton(
                onClick = {
                    uploadDestination = NativeUploadDestination.LIBRARY
                    viewModel.uploadSelectedFile(uploadDestination)
                },
            ) { Text("Library") }
            TextButton(
                onClick = {
                    uploadDestination = NativeUploadDestination.JOURNAL
                    viewModel.uploadSelectedFile(uploadDestination)
                },
            ) { Text("Journal") }
        }
        TextButton(
            onClick = {
                uploadDestination = NativeUploadDestination.OBSIDIAN_VAULT
                viewModel.uploadSelectedFile(uploadDestination)
            },
        ) { Text("Import Obsidian vault ZIP") }
        Text(
            "Choose a journal or library destination for normal files. Vault ZIPs use the Obsidian importer.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        state.pendingVaultImport?.result?.let { preview ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Vault preview", style = MaterialTheme.typography.titleMedium)
                    Text("${preview.newNotes} new, ${preview.changedNotes} changed, ${preview.unchangedNotes} unchanged")
                    Text(
                        "${preview.journalNotes} journal notes and ${preview.libraryNotes} library notes",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = viewModel::applyPendingVaultImport) { Text("Apply import") }
                        TextButton(onClick = viewModel::discardPendingVaultImport) { Text("Discard") }
                    }
                }
            }
        }
        if (state.draftCount > 0) {
            Text("${state.draftCount} encrypted offline drafts queued", style = MaterialTheme.typography.bodySmall)
            Button(onClick = { viewModel.syncDrafts() }) { Text("Sync queued drafts") }
        }
    }
}


@Composable
internal fun ThoughtPinsLibraryScreen(state: ThoughtPinsUiState, viewModel: ThoughtPinsViewModel) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        if (state.librarySources.isEmpty()) {
            ThoughtPinsEmptyState(
                title = "Nothing pinned yet",
                message = "Save an article or import a document and it will appear here.",
            )
        } else {
            LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(state.librarySources, key = { it.id }) { source ->
                    Card(Modifier.fillMaxWidth().animateItem()) {
                        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                            Text(source.title, style = MaterialTheme.typography.titleMedium)
                            Text(
                                listOfNotNull(
                                    source.publisher ?: source.sourceDomain,
                                    source.publishedAt,
                                    "${source.chunks} memory ${if (source.chunks == 1) "section" else "sections"}",
                                ).joinToString(" | "),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            source.summary?.takeIf { it.isNotBlank() }?.let {
                                Text(
                                    it,
                                    style = MaterialTheme.typography.bodyMedium,
                                    maxLines = 3,
                                    overflow = TextOverflow.Ellipsis,
                                )
                            }
                            thoughtPinsSourceUrl(source)?.let { url ->
                                TextButton(onClick = { viewModel.openLegalLink("original source", url) }) {
                                    Text("Open original")
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}


@Composable
internal fun ThoughtPinsMemoryCardsScreen(cards: List<MemoryCardResponse>, title: String) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        if (cards.isEmpty()) {
            ThoughtPinsEmptyState(
                title = "No ${title.lowercase()} yet",
                message = if (title == "People") {
                    "People you mention in your journal will gather here."
                } else {
                    "Places you write about will gather here."
                },
            )
        } else {
            LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(cards, key = { it.id }) { card ->
                    Card(Modifier.fillMaxWidth().animateItem()) {
                        Column(Modifier.padding(16.dp)) {
                            Text(card.name, style = MaterialTheme.typography.titleMedium)
                            Text(card.subtitle ?: card.type)
                            Text(
                                "${card.memoryCount} memories | ${card.relationshipCount} links",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            card.obsidianPath?.let { path ->
                                Text(
                                    "Archive: ${thoughtPinsReferenceTitle(path, card.name)}",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}


private fun thoughtPinsSourceUrl(source: LibrarySourceResponse): String? =
    listOfNotNull(source.canonicalUrl, source.sourceUrl, source.originalUrl)
        .firstOrNull { it.startsWith("https://", ignoreCase = true) || it.startsWith("http://", ignoreCase = true) }


private fun thoughtPinsReferenceTitle(path: String, fallback: String): String {
    val leaf = path.substringAfterLast('/').substringAfterLast('\\').removeSuffix(".md").trim()
    return leaf.ifBlank { fallback }
}
