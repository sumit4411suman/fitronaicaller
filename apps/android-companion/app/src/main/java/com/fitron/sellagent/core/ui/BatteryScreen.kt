package com.fitron.sellagent.core.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import com.fitron.sellagent.R
import com.fitron.sellagent.core.AppInfo
import com.fitron.sellagent.core.power.BatteryOptimization

@Composable
fun batteryLabel(ignoring: Boolean?): Pair<String, Tone> = when (ignoring) {
    true -> stringResource(R.string.battery_unrestricted) to Tone.Good
    false -> stringResource(R.string.battery_optimized) to Tone.Warn
    null -> stringResource(R.string.unknown) to Tone.Neutral
}

/** Battery optimization screen: real PowerManager state, request dialog, settings fallback, Samsung note. */
@Composable
fun BatteryScreen() {
    val context = LocalContext.current
    var tick by remember { mutableIntStateOf(0) }
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { tick++ }
    val ignoring = remember(tick) { BatteryOptimization.isIgnoring(context) }
    var lastAction by remember { mutableStateOf("") }
    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        AppHeader(stringResource(R.string.battery_title), stringResource(R.string.battery_subtitle))
        SectionCard(stringResource(R.string.battery_state)) {
            val (label, tone) = batteryLabel(ignoring)
            KeyValueRow("isIgnoringBatteryOptimizations", label, tone)
            KeyValueRow(stringResource(R.string.status_battery), AppInfo.batteryPercent(context)?.let { "$it %" } ?: "-", Tone.Neutral)
            MutedText(stringResource(R.string.battery_why))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                GoldButton(stringResource(R.string.battery_request), enabled = ignoring != true) { lastAction = BatteryOptimization.requestExemption(context) }
                OutlineButton(stringResource(R.string.battery_open_list)) { lastAction = BatteryOptimization.openSettingsList(context) }
            }
            if (lastAction.isNotBlank()) MutedText(lastAction)
        }
        SectionCard(stringResource(R.string.battery_samsung_title)) {
            MutedText(stringResource(R.string.battery_samsung_text))
            OutlineButton(stringResource(R.string.battery_open_app_details)) { BatteryOptimization.openAppDetails(context) }
        }
        Text("", modifier = Modifier.padding(8.dp))
    }
}
