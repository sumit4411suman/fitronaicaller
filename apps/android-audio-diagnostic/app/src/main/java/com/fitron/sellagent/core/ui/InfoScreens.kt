package com.fitron.sellagent.core.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.fitron.sellagent.R
import com.fitron.sellagent.core.AppInfo
import com.fitron.sellagent.protocol.PROTOCOL_VERSION

/** Help & Support: a condensed copy of docs/ANDROID_APPS.md relevant to the phone operator. */
@Composable
fun HelpScreen() {
    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        AppHeader(stringResource(R.string.help_title), stringResource(R.string.help_subtitle))
        SectionCard(stringResource(R.string.help_pairing_title)) { MutedText(stringResource(R.string.help_pairing_text)) }
        SectionCard(stringResource(R.string.help_calls_title)) { MutedText(stringResource(R.string.help_calls_text)) }
        SectionCard(stringResource(R.string.help_dialer_title)) { MutedText(stringResource(R.string.perm_dialer_why)) }
        SectionCard(stringResource(R.string.perm_limits_title)) { MutedText(stringResource(R.string.perm_limits_text)) }
        SectionCard(stringResource(R.string.help_docs_title)) { MutedText(stringResource(R.string.help_docs_text)) }
        Text("", modifier = Modifier.padding(8.dp))
    }
}

@Composable
fun AboutScreen(appDescription: Int) {
    val context = LocalContext.current
    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        BrandHeader(stringResource(R.string.splash_subtitle))
        SectionCard(stringResource(R.string.settings_about)) {
            KeyValueRow(stringResource(R.string.settings_app_version), AppInfo.appVersion(context), Tone.Neutral)
            KeyValueRow(stringResource(R.string.settings_protocol), PROTOCOL_VERSION, Tone.Neutral)
            KeyValueRow(stringResource(R.string.settings_device), AppInfo.deviceModel(), Tone.Neutral)
            KeyValueRow(stringResource(R.string.settings_android), AppInfo.androidVersion(), Tone.Neutral)
            MutedText(stringResource(appDescription))
            MutedText(stringResource(R.string.about_no_account))
        }
        Text("", modifier = Modifier.padding(8.dp))
    }
}
