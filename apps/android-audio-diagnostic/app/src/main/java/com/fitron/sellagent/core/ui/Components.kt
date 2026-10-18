package com.fitron.sellagent.core.ui

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
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.fitron.sellagent.brand.BrandColors

enum class Tone { Neutral, Good, Warn, Bad, Info }

fun Tone.color(): Color = when (this) {
    Tone.Neutral -> BrandColors.TextSecondary
    Tone.Good -> BrandColors.Success
    Tone.Warn -> BrandColors.Warning
    Tone.Bad -> BrandColors.Danger
    Tone.Info -> BrandColors.Info
}

@Composable
fun AppHeader(title: String, subtitle: String? = null) {
    Column(modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp)) {
        Text(title, style = MaterialTheme.typography.displaySmall, color = BrandColors.Gold)
        if (subtitle != null) {
            Text(subtitle, style = MaterialTheme.typography.bodySmall, color = BrandColors.TextSecondary)
        }
    }
}

@Composable
fun SectionCard(title: String, modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Card(
        modifier = modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp),
        colors = CardDefaults.cardColors(containerColor = BrandColors.Surface, contentColor = BrandColors.TextPrimary),
        border = androidx.compose.foundation.BorderStroke(1.dp, BrandColors.SurfaceBorder),
        shape = RoundedCornerShape(12.dp),
    ) {
        Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium, color = BrandColors.Gold)
            content()
        }
    }
}

@Composable
fun StatusDot(tone: Tone) {
    Box(modifier = Modifier.size(10.dp).background(tone.color(), CircleShape))
}

@Composable
fun KeyValueRow(label: String, value: String, tone: Tone = Tone.Neutral) {
    Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        StatusDot(tone)
        Spacer(Modifier.width(8.dp))
        Text(label, modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium, color = BrandColors.TextPrimary)
        Text(value, style = MaterialTheme.typography.bodyMedium, color = tone.color(), fontWeight = FontWeight.Medium)
    }
}

@Composable
fun BannerCard(text: String, tone: Tone = Tone.Warn) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 6.dp)
            .border(1.dp, tone.color(), RoundedCornerShape(10.dp))
            .background(BrandColors.SurfaceElevated, RoundedCornerShape(10.dp))
            .padding(12.dp),
    ) {
        Text(text, style = MaterialTheme.typography.bodySmall, color = BrandColors.TextPrimary)
    }
}

@Composable
fun GoldButton(text: String, modifier: Modifier = Modifier, enabled: Boolean = true, onClick: () -> Unit) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier,
        colors = ButtonDefaults.buttonColors(
            containerColor = BrandColors.Gold,
            contentColor = BrandColors.OnGold,
            disabledContainerColor = BrandColors.GoldMuted,
            disabledContentColor = BrandColors.OnGold,
        ),
    ) { Text(text) }
}

@Composable
fun OutlineButton(text: String, modifier: Modifier = Modifier, enabled: Boolean = true, onClick: () -> Unit) {
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier,
        colors = ButtonDefaults.outlinedButtonColors(contentColor = BrandColors.Gold, disabledContentColor = BrandColors.TextDisabled),
        border = androidx.compose.foundation.BorderStroke(1.dp, if (enabled) BrandColors.Gold else BrandColors.SurfaceBorder),
    ) { Text(text) }
}

@Composable
fun DangerButton(text: String, modifier: Modifier = Modifier, enabled: Boolean = true, onClick: () -> Unit) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier,
        colors = ButtonDefaults.buttonColors(
            containerColor = BrandColors.EmergencyStop,
            contentColor = Color.White,
            disabledContainerColor = BrandColors.SurfaceBorder,
            disabledContentColor = BrandColors.TextDisabled,
        ),
    ) { Text(text, fontWeight = FontWeight.Bold) }
}

@Composable
fun LogList(lines: List<String>, maxLines: Int = 12) {
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        lines.takeLast(maxLines).forEach { line ->
            Text(line, style = MaterialTheme.typography.labelSmall, color = BrandColors.TextSecondary)
        }
        if (lines.isEmpty()) Spacer(Modifier.height(4.dp))
    }
}
