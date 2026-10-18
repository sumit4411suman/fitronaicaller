// Shared Compose theme for both Android apps. Generated from packages/brand/tokens.json.
// Copy verbatim into each app's ui/theme package (package line adjusted). Keep identical across apps.
package com.fitron.sellagent.brand

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

object BrandColors {
    val Background = Color(0xFF0B0B0B)
    val Surface = Color(0xFF141414)
    val SurfaceElevated = Color(0xFF1C1C1C)
    val SurfaceBorder = Color(0xFF2A2A2A)
    val Gold = Color(0xFFD4AF37)
    val GoldLight = Color(0xFFE6C85A)
    val GoldDark = Color(0xFFB8962E)
    val GoldMuted = Color(0xFF8A7124)
    val TextPrimary = Color(0xFFF5F0E1)
    val TextSecondary = Color(0xFFB8B2A0)
    val TextDisabled = Color(0xFF6E6A5E)
    val OnGold = Color(0xFF0B0B0B)
    val Success = Color(0xFF4CAF50)
    val Warning = Color(0xFFE6A23C)
    val Danger = Color(0xFFE05252)
    val Info = Color(0xFF5B9BD5)
    val EmergencyStop = Color(0xFFC62828)
}

// The brand is dark-only (gold on near-black), exactly like the FITRON logo. Light mode is intentionally not offered.
private val BrandColorScheme = darkColorScheme(
    primary = BrandColors.Gold,
    onPrimary = BrandColors.OnGold,
    primaryContainer = BrandColors.GoldDark,
    onPrimaryContainer = BrandColors.OnGold,
    secondary = BrandColors.GoldLight,
    onSecondary = BrandColors.OnGold,
    tertiary = BrandColors.GoldMuted,
    background = BrandColors.Background,
    onBackground = BrandColors.TextPrimary,
    surface = BrandColors.Surface,
    onSurface = BrandColors.TextPrimary,
    surfaceVariant = BrandColors.SurfaceElevated,
    onSurfaceVariant = BrandColors.TextSecondary,
    outline = BrandColors.SurfaceBorder,
    error = BrandColors.Danger,
    onError = Color.White,
)

val BrandTypography = Typography(
    displaySmall = TextStyle(fontSize = 28.sp, fontWeight = FontWeight.Bold, letterSpacing = 2.sp),
    titleLarge = TextStyle(fontSize = 20.sp, fontWeight = FontWeight.SemiBold),
    titleMedium = TextStyle(fontSize = 16.sp, fontWeight = FontWeight.Medium),
    bodyMedium = TextStyle(fontSize = 14.sp),
    bodySmall = TextStyle(fontSize = 12.sp),
    labelSmall = TextStyle(fontSize = 11.sp),
)

@Composable
fun SellAgentTheme(content: @Composable () -> Unit) {
    @Suppress("UNUSED_VARIABLE") val ignoredSystemDark = isSystemInDarkTheme() // brand is always dark
    MaterialTheme(colorScheme = BrandColorScheme, typography = BrandTypography, content = content)
}
