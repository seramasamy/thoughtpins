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


@Composable
internal fun PinMark(modifier: Modifier = Modifier, tint: Color, grooveColor: Color? = null) {
    val resolvedGrooveColor = grooveColor ?: MaterialTheme.colorScheme.surface
    Canvas(modifier) {
        val s = size.minDimension / 128f
        val silhouette = Path().apply {
            moveTo(64f * s, 17f * s)
            cubicTo(39.7f * s, 17f * s, 22f * s, 34.4f * s, 22f * s, 57.5f * s)
            cubicTo(22f * s, 78.3f * s, 37.7f * s, 94.9f * s, 64f * s, 121f * s)
            cubicTo(90.3f * s, 94.9f * s, 106f * s, 78.3f * s, 106f * s, 57.5f * s)
            cubicTo(106f * s, 34.4f * s, 88.3f * s, 17f * s, 64f * s, 17f * s)
            close()
        }
        val grooves = Path().apply {
            moveTo(64f * s, 29f * s)
            lineTo(64f * s, 93f * s)
            moveTo(53f * s, 29f * s)
            cubicTo(45f * s, 26f * s, 40f * s, 31f * s, 40f * s, 38f * s)
            cubicTo(40f * s, 44f * s, 44f * s, 47f * s, 50f * s, 48f * s)
            moveTo(39f * s, 41f * s)
            cubicTo(32f * s, 45f * s, 31f * s, 54f * s, 35f * s, 60f * s)
            cubicTo(39f * s, 65f * s, 44f * s, 65f * s, 50f * s, 62f * s)
            moveTo(35f * s, 63f * s)
            cubicTo(33f * s, 72f * s, 37f * s, 80f * s, 45f * s, 82f * s)
            cubicTo(52f * s, 84f * s, 55f * s, 88f * s, 55f * s, 93f * s)
            moveTo(75f * s, 29f * s)
            cubicTo(83f * s, 26f * s, 88f * s, 31f * s, 88f * s, 38f * s)
            cubicTo(88f * s, 44f * s, 84f * s, 47f * s, 78f * s, 48f * s)
            moveTo(89f * s, 41f * s)
            cubicTo(96f * s, 45f * s, 97f * s, 54f * s, 93f * s, 60f * s)
            cubicTo(89f * s, 65f * s, 84f * s, 65f * s, 78f * s, 62f * s)
            moveTo(93f * s, 63f * s)
            cubicTo(95f * s, 72f * s, 91f * s, 80f * s, 83f * s, 82f * s)
            cubicTo(76f * s, 84f * s, 73f * s, 88f * s, 73f * s, 93f * s)
        }
        withTransform({
            scale(0.94f, 0.94f)
            translate(3.84f * s, -1.16f * s)
        }) {
            drawPath(silhouette, color = tint)
            drawPath(
                grooves,
                color = resolvedGrooveColor,
                style = Stroke(width = 5.5f * s, cap = StrokeCap.Round, join = StrokeJoin.Round),
            )
        }
    }
}

@Composable
internal fun ThoughtPinsBrandMark(modifier: Modifier = Modifier) {
    Box(
        modifier
            .background(TerracottaBrand, RoundedCornerShape(16.dp))
            .padding(8.dp),
        contentAlignment = Alignment.Center,
    ) {
        PinMark(Modifier.fillMaxSize(), tint = Color.White, grooveColor = TerracottaBrand)
    }
}

// Conservative reduced-motion gate: honor the system animator duration scale.
@Composable
internal fun rememberAnimationsEnabled(): Boolean {
    val context = LocalContext.current
    return remember {
        runCatching {
            AndroidSystemSettings.Global.getFloat(
                context.contentResolver,
                AndroidSystemSettings.Global.ANIMATOR_DURATION_SCALE,
                1f,
            )
        }.getOrDefault(1f) > 0f
    }
}

// The brand three-dot pulse: opacity 0.25 to 1, 1.2s loop, 160ms stagger.
// Collapses to static dots when system animations are disabled.
@Composable
internal fun ThinkingDots(modifier: Modifier = Modifier) {
    val animationsEnabled = rememberAnimationsEnabled()
    val dotColor = MaterialTheme.colorScheme.primary
    if (!animationsEnabled) {
        Row(modifier, horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
            repeat(3) {
                Box(Modifier.size(6.dp).background(dotColor, CircleShape))
            }
        }
        return
    }
    val transition = rememberInfiniteTransition(label = "thinking")
    val alphas = List(3) { index ->
        transition.animateFloat(
            initialValue = 0.25f,
            targetValue = 1f,
            animationSpec = infiniteRepeatable(
                animation = tween(durationMillis = 600, easing = LinearEasing),
                repeatMode = RepeatMode.Reverse,
                initialStartOffset = StartOffset(index * 160),
            ),
            label = "thinking-dot-$index",
        )
    }
    Row(modifier, horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
        alphas.forEach { alpha ->
            Box(Modifier.size(6.dp).background(dotColor.copy(alpha = alpha.value), CircleShape))
        }
    }
}

// Empty states: the pin glyph at low opacity, one serif line, one sans sentence.
@Composable
internal fun ThoughtPinsEmptyState(title: String, message: String) {
    Column(
        Modifier.fillMaxWidth().padding(horizontal = 24.dp, vertical = 48.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        PinMark(Modifier.size(56.dp), tint = TerracottaBrand.copy(alpha = 0.3f))
        Text(title, style = MaterialTheme.typography.titleLarge, textAlign = TextAlign.Center)
        Text(
            message,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
    }
}

// Persistent maintenance banner, visually distinct from transient snackbars.
@Composable
internal fun MaintenanceBanner(message: String) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        color = MaterialTheme.colorScheme.tertiaryContainer,
        contentColor = MaterialTheme.colorScheme.onTertiaryContainer,
    ) {
        Column(Modifier.padding(horizontal = 16.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text("Maintenance", style = MaterialTheme.typography.labelMedium)
            Text(
                message,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
            )
        }
    }
}
