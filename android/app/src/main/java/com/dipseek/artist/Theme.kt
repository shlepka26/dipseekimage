package com.dipseek.artist

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// Цвета взяты из палитры «neon» движка — приложение выглядит как свои же постеры.
private val Scheme = darkColorScheme(
    primary = Color(0xFFF72585),
    onPrimary = Color(0xFFFFFFFF),
    secondary = Color(0xFF4CC9F0),
    onSecondary = Color(0xFF05010F),
    background = Color(0xFF0B0B10),
    onBackground = Color(0xFFE8ECF4),
    surface = Color(0xFF14141C),
    onSurface = Color(0xFFE8ECF4),
    surfaceVariant = Color(0xFF20202C),
    onSurfaceVariant = Color(0xFF9AA4B8),
    error = Color(0xFFFF6B6B),
    onError = Color(0xFF1A0505),
    outline = Color(0xFF33333F),
)

@Composable
fun DipseekTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = Scheme, content = content)
}
