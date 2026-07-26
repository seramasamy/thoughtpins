package com.thoughtpins.app.ui

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Chat
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.outlined.CalendarMonth
import androidx.compose.material.icons.outlined.People
import androidx.compose.material.icons.outlined.Place
import androidx.compose.material.icons.outlined.PushPin
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.unit.dp


@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun ThoughtPinsMainShell(
    state: ThoughtPinsUiState,
    viewModel: ThoughtPinsViewModel,
    voiceRecorder: NativeVoiceRecorder,
) {
    var tab by rememberSaveable { mutableStateOf("Chat") }
    val snackbarHostState = remember { SnackbarHostState() }
    LaunchedEffect(state.banner) {
        val message = state.banner ?: return@LaunchedEffect
        snackbarHostState.showSnackbar(message)
        viewModel.clearBanner()
    }
    val tabs = listOf(
        Triple("Recap", Icons.Outlined.CalendarMonth, "Recap"),
        Triple("People", Icons.Outlined.People, "People"),
        Triple("Chat", Icons.AutoMirrored.Outlined.Chat, "Chat"),
        Triple("Places", Icons.Outlined.Place, "Places"),
        Triple("Pins", Icons.Outlined.PushPin, "Pins"),
    )
    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        topBar = {
            CenterAlignedTopAppBar(
                title = { Text(tab, style = MaterialTheme.typography.titleLarge) },
                actions = {
                    IconButton(onClick = { tab = "Capture" }) {
                        Icon(Icons.Filled.Add, contentDescription = "Capture")
                    }
                    IconButton(onClick = { tab = "Account" }) {
                        Icon(Icons.Filled.Settings, contentDescription = "Settings")
                    }
                },
            )
        },
        snackbarHost = { SnackbarHost(snackbarHostState) },
        bottomBar = {
            NavigationBar(
                containerColor = MaterialTheme.colorScheme.surface,
                tonalElevation = 0.dp,
            ) {
                tabs.forEach { (item, icon, description) ->
                    val selected = tab == item
                    NavigationBarItem(
                        selected = selected,
                        onClick = { tab = item },
                        label = { Text(item, style = MaterialTheme.typography.labelSmall) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = MaterialTheme.colorScheme.primary,
                            selectedTextColor = MaterialTheme.colorScheme.primary,
                            indicatorColor = MaterialTheme.colorScheme.surface,
                            unselectedIconColor = MaterialTheme.colorScheme.onSurfaceVariant,
                            unselectedTextColor = MaterialTheme.colorScheme.onSurfaceVariant,
                        ),
                        icon = {
                            if (item == "Chat") {
                                Box(
                                    Modifier
                                        .size(44.dp)
                                        .shadow(7.dp, CircleShape, clip = false)
                                        .background(MaterialTheme.colorScheme.primary, CircleShape)
                                        .border(2.dp, MaterialTheme.colorScheme.surface, CircleShape),
                                    contentAlignment = Alignment.Center,
                                ) {
                                    Icon(
                                        icon,
                                        contentDescription = description,
                                        modifier = Modifier.size(22.dp),
                                        tint = MaterialTheme.colorScheme.onPrimary,
                                    )
                                }
                            } else {
                                Box(Modifier.size(28.dp), contentAlignment = Alignment.Center) {
                                    Icon(icon, contentDescription = description, modifier = Modifier.size(21.dp))
                                    if (selected) {
                                        Box(
                                            Modifier
                                                .align(Alignment.BottomCenter)
                                                .size(3.dp)
                                                .background(MaterialTheme.colorScheme.primary, CircleShape),
                                        )
                                    }
                                }
                            }
                        },
                    )
                }
            }
        },
    ) { padding ->
        Column(Modifier.padding(padding).fillMaxSize()) {
            state.maintenanceMessage?.let { MaintenanceBanner(it) }
            val animationsEnabled = rememberAnimationsEnabled()
            val tabDuration = if (animationsEnabled) 220 else 0
            AnimatedContent(
                targetState = tab,
                transitionSpec = {
                    fadeIn(animationSpec = tween(tabDuration, delayMillis = tabDuration / 2)) togetherWith
                        fadeOut(animationSpec = tween(tabDuration / 2))
                },
                label = "tab-switch",
                modifier = Modifier.weight(1f),
            ) { current ->
                Column(Modifier.fillMaxSize().padding(16.dp)) {
                    when (current) {
                        "Recap" -> ThoughtPinsRecapScreen(state, viewModel)
                        "People" -> ThoughtPinsMemoryCardsScreen(state.memoryCards, "People")
                        "Chat" -> ThoughtPinsChatScreen(state, viewModel, voiceRecorder)
                        "Places" -> ThoughtPinsMemoryCardsScreen(state.placeCards, "Places")
                        "Pins" -> ThoughtPinsLibraryScreen(state, viewModel)
                        "Capture" -> ThoughtPinsCaptureScreen(state, viewModel)
                        else -> ThoughtPinsAccountScreen(state, viewModel)
                    }
                }
            }
        }
    }
}
