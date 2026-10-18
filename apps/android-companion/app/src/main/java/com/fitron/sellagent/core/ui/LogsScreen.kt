package com.fitron.sellagent.core.ui

import android.content.Intent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fitron.sellagent.R
import com.fitron.sellagent.brand.BrandColors
import com.fitron.sellagent.core.AppInfo
import com.fitron.sellagent.core.log.AppLog
import com.fitron.sellagent.core.log.LogLevel

/** Logs screen: filter by minimum level, share as text, clear. Content is already sanitized by AppLog. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LogsScreen() {
    val context = LocalContext.current
    val entries by AppLog.entries.collectAsStateWithLifecycle()
    var minLevel by rememberSaveable { mutableStateOf(LogLevel.INFO) }
    val visible = entries.filter { it.level.ordinal >= minLevel.ordinal }.asReversed()
    LazyColumn(modifier = Modifier.fillMaxSize()) {
        item {
            AppHeader(stringResource(R.string.logs_title), stringResource(R.string.logs_subtitle, entries.size))
            Row(modifier = Modifier.padding(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                LogLevel.entries.forEach { lvl ->
                    FilterChip(
                        selected = minLevel == lvl,
                        onClick = { minLevel = lvl },
                        label = { Text(lvl.name) },
                        colors = FilterChipDefaults.filterChipColors(selectedContainerColor = BrandColors.ChipWarningBg, selectedLabelColor = BrandColors.GoldDark),
                    )
                }
            }
            Row(modifier = Modifier.padding(horizontal = 16.dp, vertical = 6.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                GoldButton(stringResource(R.string.logs_share), enabled = visible.isNotEmpty()) {
                    val header = "SELL AGENT log · ${AppInfo.deviceModel()} · ${AppInfo.androidVersion()} · app ${AppInfo.appVersion(context)}\n"
                    val text = header + AppLog.asText(LogLevel.entries.filter { it.ordinal >= minLevel.ordinal }.toSet())
                    val intent = Intent(Intent.ACTION_SEND).apply {
                        type = "text/plain"
                        putExtra(Intent.EXTRA_SUBJECT, "SELL AGENT log")
                        putExtra(Intent.EXTRA_TEXT, text.takeLast(200_000))
                    }
                    runCatching { context.startActivity(Intent.createChooser(intent, "SELL AGENT log")) }
                }
                DangerOutlineButton(stringResource(R.string.logs_clear)) { AppLog.clear() }
            }
            SectionCard { MutedText(stringResource(R.string.logs_privacy)) }
            if (visible.isEmpty()) SectionCard { MutedText(stringResource(R.string.logs_empty)) }
        }
        items(visible) { e ->
            val tone = when (e.level) {
                LogLevel.ERROR -> Tone.Bad
                LogLevel.WARN -> Tone.Warn
                LogLevel.INFO -> Tone.Info
                LogLevel.DEBUG -> Tone.Neutral
            }
            Row(modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 3.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                StatusDot(tone)
                Text("${e.time} [${e.tag}] ${e.message}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurface)
            }
        }
    }
}
