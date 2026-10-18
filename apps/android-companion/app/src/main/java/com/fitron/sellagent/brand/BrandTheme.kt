// Shared Compose theme for both Android apps. Generated from packages/brand/tokens.json.
// Copy verbatim into each app's ui/theme package (package line adjusted). Keep identical across apps.
// Design (approved mockups): splash + live-call screens use the DARK scheme (gold on near-black, like the FITRON logo);
// every other screen uses the LIGHT scheme (off-white surfaces, dark text, gold primary buttons).
package com.fitron.sellagent.brand

import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
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
    val ContentBackground = Color(0xFFF7F6F2)
    val ContentSurface = Color(0xFFFFFFFF)
    val ContentBorder = Color(0xFFE6E2D6)
    val TextOnLight = Color(0xFF1A1A1A)
    val TextOnLightSecondary = Color(0xFF6B665A)
    val ChipSuccessBg = Color(0xFFE6F4EA)
    val ChipWarningBg = Color(0xFFFFF4E0)
    val ChipDangerBg = Color(0xFFFDE8E8)
    val ChipInfoBg = Color(0xFFE8F0FA)
    val ChipNeutralBg = Color(0xFFF0EEE6)
}

val BrandDarkScheme: ColorScheme = darkColorScheme(
    primary = BrandColors.Gold, onPrimary = BrandColors.OnGold,
    primaryContainer = BrandColors.GoldDark, onPrimaryContainer = BrandColors.OnGold,
    secondary = BrandColors.GoldLight, onSecondary = BrandColors.OnGold, tertiary = BrandColors.GoldMuted,
    background = BrandColors.Background, onBackground = BrandColors.TextPrimary,
    surface = BrandColors.Surface, onSurface = BrandColors.TextPrimary,
    surfaceVariant = BrandColors.SurfaceElevated, onSurfaceVariant = BrandColors.TextSecondary,
    outline = BrandColors.SurfaceBorder, error = BrandColors.Danger, onError = Color.White,
)

val BrandLightScheme: ColorScheme = lightColorScheme(
    primary = BrandColors.Gold, onPrimary = BrandColors.OnGold,
    primaryContainer = BrandColors.GoldLight, onPrimaryContainer = BrandColors.OnGold,
    secondary = BrandColors.GoldDark, onSecondary = Color.White, tertiary = BrandColors.GoldMuted,
    background = BrandColors.ContentBackground, onBackground = BrandColors.TextOnLight,
    surface = BrandColors.ContentSurface, onSurface = BrandColors.TextOnLight,
    surfaceVariant = BrandColors.ChipNeutralBg, onSurfaceVariant = BrandColors.TextOnLightSecondary,
    outline = BrandColors.ContentBorder, error = BrandColors.EmergencyStop, onError = Color.White,
)

val BrandTypography = Typography(
    displaySmall = TextStyle(fontSize = 28.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp),
    titleLarge = TextStyle(fontSize = 20.sp, fontWeight = FontWeight.SemiBold),
    titleMedium = TextStyle(fontSize = 16.sp, fontWeight = FontWeight.Medium),
    bodyMedium = TextStyle(fontSize = 14.sp),
    bodySmall = TextStyle(fontSize = 12.sp),
    labelSmall = TextStyle(fontSize = 11.sp),
)

/** Light scheme for ordinary screens; pass dark = true for splash and the live-call screen. */
@Composable
fun SellAgentTheme(dark: Boolean = false, content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (dark) BrandDarkScheme else BrandLightScheme, typography = BrandTypography, content = content)
}
