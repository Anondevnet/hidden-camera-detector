package net.anondevnet.hcd.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val colors = darkColorScheme(
    primary = Color(0xFFE8A04A),
    onPrimary = Color(0xFF1A1308),
    background = Color(0xFF12100E),
    onBackground = Color(0xFFF4EFE6),
    surface = Color(0xFF1C1814),
    onSurface = Color(0xFFF4EFE6),
    secondary = Color(0xFFD46EC8),
)

@Composable
fun HcdTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = colors, content = content)
}
