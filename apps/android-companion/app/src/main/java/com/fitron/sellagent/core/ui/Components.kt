package com.fitron.sellagent.core.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextFieldColors
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.fitron.sellagent.R
import com.fitron.sellagent.brand.BrandColors

enum class Tone { Neutral, Good, Warn, Bad, Info }

/** True while the composition runs under SellAgentTheme(dark = true). */
@Composable
fun isDarkScheme(): Boolean = MaterialTheme.colorScheme.background == BrandColors.Background

@Composable
fun Tone.color(): Color = when (this) {
    Tone.Neutral -> MaterialTheme.colorScheme.onSurfaceVariant
    Tone.Good -> BrandColors.Success
    Tone.Warn -> BrandColors.Warning
    Tone.Bad -> if (isDarkScheme()) BrandColors.Danger else BrandColors.EmergencyStop
    Tone.Info -> BrandColors.Info
}

@Composable
fun Tone.chipBackground(): Color = if (isDarkScheme()) {
    BrandColors.SurfaceElevated
} else when (this) {
    Tone.Neutral -> BrandColors.ChipNeutralBg
    Tone.Good -> BrandColors.ChipSuccessBg
    Tone.Warn -> BrandColors.ChipWarningBg
    Tone.Bad -> BrandColors.ChipDangerBg
    Tone.Info -> BrandColors.ChipInfoBg
}

/** Screen header: title in the on-background colour, optional subtitle, optional trailing action icon. */
@Composable
fun AppHeader(title: String, subtitle: String? = null, action: ImageVector? = null, actionDescription: String? = null, onAction: (() -> Unit)? = null) {
    Row(modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(modifier = Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.displaySmall, color = MaterialTheme.colorScheme.onBackground)
            if (subtitle != null) Text(subtitle, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if (action != null && onAction != null) {
            IconButton(onClick = onAction) { Icon(action, contentDescription = actionDescription, tint = MaterialTheme.colorScheme.onBackground) }
        }
    }
}

/** Header with the FITRON mark and the two-tone "SELL AGENT" word mark. */
@Composable
fun BrandHeader(subtitle: String? = null, action: ImageVector? = null, actionDescription: String? = null, onAction: (() -> Unit)? = null) {
    Row(modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
        LogoMark(size = 40.dp)
        Spacer(Modifier.width(12.dp))
        Column(modifier = Modifier.weight(1f)) {
            WordMark(style = MaterialTheme.typography.titleLarge)
            if (subtitle != null) Text(subtitle, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if (action != null && onAction != null) {
            IconButton(onClick = onAction) { Icon(action, contentDescription = actionDescription, tint = MaterialTheme.colorScheme.onBackground) }
        }
    }
}

@Composable
fun LogoMark(size: Dp) {
    Box(modifier = Modifier.size(size).background(BrandColors.Background, CircleShape), contentAlignment = Alignment.Center) {
        Icon(painterResource(R.drawable.ic_logo_mark), contentDescription = null, tint = Color.Unspecified, modifier = Modifier.size(size))
    }
}

/** "SELL AGENT" with the second word in gold. */
@Composable
fun WordMark(style: androidx.compose.ui.text.TextStyle = MaterialTheme.typography.displaySmall, textAlign: TextAlign? = null) {
    Row {
        Text("SELL ", style = style, color = MaterialTheme.colorScheme.onBackground, fontWeight = FontWeight.Bold, textAlign = textAlign)
        Text("AGENT", style = style, color = BrandColors.Gold, fontWeight = FontWeight.Bold, textAlign = textAlign)
    }
}

@Composable
fun SectionCard(title: String? = null, modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Card(
        modifier = modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface, contentColor = MaterialTheme.colorScheme.onSurface),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
        shape = RoundedCornerShape(14.dp),
    ) {
        Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (title != null) Text(title, style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onSurface, fontWeight = FontWeight.SemiBold)
            content()
        }
    }
}

@Composable
fun StatusDot(tone: Tone) {
    Box(modifier = Modifier.size(10.dp).background(tone.color(), CircleShape))
}

/** Tinted pill, e.g. "Connected to PC". */
@Composable
fun StatusChip(text: String, tone: Tone, modifier: Modifier = Modifier) {
    Row(
        modifier = modifier.background(tone.chipBackground(), RoundedCornerShape(50)).padding(horizontal = 10.dp, vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        StatusDot(tone)
        Spacer(Modifier.width(6.dp))
        Text(text, style = MaterialTheme.typography.labelSmall, color = tone.color(), fontWeight = FontWeight.Medium)
    }
}

@Composable
fun KeyValueRow(label: String, value: String, tone: Tone = Tone.Neutral) {
    Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        StatusDot(tone)
        Spacer(Modifier.width(8.dp))
        Text(label, modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurface)
        Text(value, style = MaterialTheme.typography.bodyMedium, color = tone.color(), fontWeight = FontWeight.Medium, textAlign = TextAlign.End, modifier = Modifier.weight(1f))
    }
}

@Composable
fun MutedText(text: String) {
    Text(text, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
}

@Composable
fun BannerCard(text: String, tone: Tone = Tone.Warn) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 6.dp)
            .border(1.dp, tone.color(), RoundedCornerShape(10.dp))
            .background(tone.chipBackground(), RoundedCornerShape(10.dp))
            .padding(12.dp),
    ) {
        Text(text, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurface)
    }
}

@Composable
fun GoldButton(text: String, modifier: Modifier = Modifier, enabled: Boolean = true, onClick: () -> Unit) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier,
        shape = RoundedCornerShape(12.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = BrandColors.Gold,
            contentColor = BrandColors.OnGold,
            disabledContainerColor = if (isDarkScheme()) BrandColors.GoldMuted else BrandColors.ChipNeutralBg,
            disabledContentColor = if (isDarkScheme()) BrandColors.OnGold else BrandColors.TextOnLightSecondary,
        ),
    ) { Text(text, fontWeight = FontWeight.SemiBold) }
}

@Composable
fun OutlineButton(text: String, modifier: Modifier = Modifier, enabled: Boolean = true, onClick: () -> Unit) {
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier,
        shape = RoundedCornerShape(12.dp),
        colors = ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.onSurface, disabledContentColor = MaterialTheme.colorScheme.onSurfaceVariant),
        border = BorderStroke(1.dp, if (enabled) BrandColors.Gold else MaterialTheme.colorScheme.outline),
    ) { Text(text) }
}

/** Red is reserved for End Call / Emergency Stop. */
@Composable
fun DangerButton(text: String, modifier: Modifier = Modifier, enabled: Boolean = true, onClick: () -> Unit) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier,
        shape = RoundedCornerShape(12.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = BrandColors.EmergencyStop,
            contentColor = Color.White,
            disabledContainerColor = MaterialTheme.colorScheme.outline,
            disabledContentColor = MaterialTheme.colorScheme.onSurfaceVariant,
        ),
    ) { Text(text, fontWeight = FontWeight.Bold) }
}

/** Red outlined variant (e.g. Disconnect). */
@Composable
fun DangerOutlineButton(text: String, modifier: Modifier = Modifier, enabled: Boolean = true, onClick: () -> Unit) {
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier,
        shape = RoundedCornerShape(12.dp),
        colors = ButtonDefaults.outlinedButtonColors(contentColor = BrandColors.EmergencyStop, disabledContentColor = MaterialTheme.colorScheme.onSurfaceVariant),
        border = BorderStroke(1.dp, if (enabled) BrandColors.EmergencyStop else MaterialTheme.colorScheme.outline),
    ) { Text(text, fontWeight = FontWeight.SemiBold) }
}

/** Round action button (Dial / End / Speaker) as in the Home mockup. */
@Composable
fun RoundAction(icon: ImageVector, label: String, color: Color, enabled: Boolean, onClick: () -> Unit) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        val bg = if (enabled) color else MaterialTheme.colorScheme.outline
        IconButton(
            onClick = onClick,
            enabled = enabled,
            modifier = Modifier.size(64.dp).background(bg, CircleShape),
        ) { Icon(icon, contentDescription = label, tint = if (enabled) Color.White else MaterialTheme.colorScheme.onSurfaceVariant) }
        Spacer(Modifier.height(4.dp))
        Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
fun brandFieldColors(): TextFieldColors = OutlinedTextFieldDefaults.colors(
    focusedBorderColor = BrandColors.Gold,
    unfocusedBorderColor = MaterialTheme.colorScheme.outline,
    focusedLabelColor = BrandColors.GoldDark,
    unfocusedLabelColor = MaterialTheme.colorScheme.onSurfaceVariant,
    cursorColor = BrandColors.Gold,
    focusedTextColor = MaterialTheme.colorScheme.onSurface,
    unfocusedTextColor = MaterialTheme.colorScheme.onSurface,
)

@Composable
fun LogList(lines: List<String>, maxLines: Int = 12) {
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        lines.takeLast(maxLines).forEach { line ->
            Text(line, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if (lines.isEmpty()) Spacer(Modifier.height(4.dp))
    }
}
