package com.fitron.sellagent.companion.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Phone
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.fitron.sellagent.R
import com.fitron.sellagent.brand.BrandColors
import com.fitron.sellagent.companion.Routes
import com.fitron.sellagent.core.ui.AppHeader
import com.fitron.sellagent.core.ui.SectionCard

@Composable
fun MoreScreen(navigate: (String) -> Unit) {
    val items = listOf(
        Triple(Icons.Filled.Phone, R.string.more_device_connection, Routes.CONNECTION),
        Triple(Icons.Filled.Build, R.string.diag_title, Routes.DIAGNOSTICS),
        Triple(Icons.Filled.Notifications, R.string.mic_test_title, Routes.MIC_TEST),
        Triple(Icons.Filled.Notifications, R.string.speaker_test_title, Routes.SPEAKER_TEST),
        Triple(Icons.Filled.Call, R.string.route_title, Routes.AUDIO_ROUTE),
        Triple(Icons.Filled.Home, R.string.battery_title, Routes.BATTERY),
        Triple(Icons.Filled.Warning, R.string.ts_title, Routes.TROUBLESHOOTING),
        Triple(Icons.Filled.List, R.string.logs_title, Routes.LOGS),
        Triple(Icons.Filled.Lock, R.string.perm_title, Routes.PERMISSIONS),
        Triple(Icons.Filled.Settings, R.string.nav_settings, Routes.SETTINGS),
        Triple(Icons.Filled.Info, R.string.help_title, Routes.HELP),
        Triple(Icons.Filled.Star, R.string.settings_about, Routes.ABOUT),
    )
    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        AppHeader(stringResource(R.string.nav_more))
        SectionCard {
            items.forEachIndexed { i, (icon, label, route) ->
                MoreRow(icon, stringResource(label), BrandColors.GoldDark) { navigate(route) }
                if (i < items.lastIndex) HorizontalDivider(color = MaterialTheme.colorScheme.outline)
            }
        }
        SectionCard { MoreRow(Icons.Filled.Warning, stringResource(R.string.emergency_title), BrandColors.EmergencyStop) { navigate(Routes.EMERGENCY) } }
        Spacer(Modifier.height(16.dp))
    }
}

@Composable
private fun MoreRow(icon: ImageVector, label: String, tint: Color, onClick: () -> Unit) {
    Row(modifier = Modifier.fillMaxWidth().clickable(onClick = onClick).padding(vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
        Icon(icon, contentDescription = null, tint = tint)
        Spacer(Modifier.width(12.dp))
        Text(label, modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurface)
        Icon(Icons.Filled.KeyboardArrowRight, contentDescription = label, tint = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
