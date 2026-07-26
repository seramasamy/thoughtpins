package com.thoughtpins.app.ui

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
// Design tokens from DESIGN_SYSTEM.md: warm paper neutrals, terracotta accent.
// The brand terracotta is reserved for fills and brand moments; the deeper
// action tone is the AA-safe text/button color on light surfaces.
internal val TerracottaBrand = Color(0xFFE8612B)

internal val ThoughtPinsLightColorScheme = lightColorScheme(
    primary = Color(0xFFB33E16),
    onPrimary = Color(0xFFFFFFFF),
    primaryContainer = Color(0xFFFBE9DD),
    onPrimaryContainer = Color(0xFF5A2A18),
    secondary = Color(0xFF587465),
    onSecondary = Color(0xFFFFFFFF),
    secondaryContainer = Color(0xFFE6EDE7),
    onSecondaryContainer = Color(0xFF23372E),
    tertiary = Color(0xFF44708A),
    onTertiary = Color(0xFFFFFFFF),
    tertiaryContainer = Color(0xFFE4EDF2),
    onTertiaryContainer = Color(0xFF223B4C),
    background = Color(0xFFF8F8F6),
    onBackground = Color(0xFF221D16),
    surface = Color(0xFFFFFFFF),
    onSurface = Color(0xFF221D16),
    surfaceVariant = Color(0xFFFCFBF9),
    onSurfaceVariant = Color(0xFF6B6459),
    outline = Color(0xFFD5CFC7),
    outlineVariant = Color(0xFFE6E2DD),
    error = Color(0xFFA83232),
    onError = Color(0xFFFFFFFF),
)

internal val ThoughtPinsDarkColorScheme = darkColorScheme(
    primary = Color(0xFFE8895F),
    onPrimary = Color(0xFF471A08),
    primaryContainer = Color(0xFF6E3014),
    onPrimaryContainer = Color(0xFFFBE9DD),
    secondary = Color(0xFF9CBBA9),
    onSecondary = Color(0xFF243830),
    secondaryContainer = Color(0xFF3A4A41),
    onSecondaryContainer = Color(0xFFE6EDE7),
    tertiary = Color(0xFF9FC0D4),
    onTertiary = Color(0xFF1E3646),
    tertiaryContainer = Color(0xFF2C4658),
    onTertiaryContainer = Color(0xFFE4EDF2),
    background = Color(0xFF1A1714),
    onBackground = Color(0xFFF4EFE8),
    surface = Color(0xFF221D18),
    onSurface = Color(0xFFF4EFE8),
    surfaceVariant = Color(0xFF332C24),
    onSurfaceVariant = Color(0xFFB5AC9F),
    outline = Color(0xFF564E42),
    outlineVariant = Color(0xFF3C352C),
    error = Color(0xFFE59A9A),
    onError = Color(0xFF3C1313),
)

// Serif display faces for titles and brand moments, platform sans for body.
// All Material 3 defaults keep sp units; only families change here.
internal val ThoughtPinsTypography = Typography().let { base ->
    base.copy(
        displayLarge = base.displayLarge.copy(fontFamily = FontFamily.Serif),
        displayMedium = base.displayMedium.copy(fontFamily = FontFamily.Serif),
        displaySmall = base.displaySmall.copy(fontFamily = FontFamily.Serif),
        headlineLarge = base.headlineLarge.copy(fontFamily = FontFamily.Serif),
        headlineMedium = base.headlineMedium.copy(fontFamily = FontFamily.Serif),
        headlineSmall = base.headlineSmall.copy(fontFamily = FontFamily.Serif),
        titleLarge = base.titleLarge.copy(fontFamily = FontFamily.Serif),
    )
}

// Radius stays at or below 8dp per the design system; pills remain full-round.
internal val ThoughtPinsShapes = Shapes(
    extraSmall = RoundedCornerShape(8.dp),
    small = RoundedCornerShape(6.dp),
    medium = RoundedCornerShape(8.dp),
    large = RoundedCornerShape(8.dp),
)

// Canonical 128-unit memory-pin geometry shared with the web and launcher assets.
