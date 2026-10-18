package com.fitron.sellagent.companion.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fitron.sellagent.R
import com.fitron.sellagent.core.core
import com.fitron.sellagent.core.ui.AppHeader
import com.fitron.sellagent.core.ui.KeyValueRow
import com.fitron.sellagent.core.ui.MutedText
import com.fitron.sellagent.core.ui.SectionCard
import com.fitron.sellagent.core.ui.StatusChip
import com.fitron.sellagent.core.ui.connectionChip
import com.fitron.sellagent.core.ui.connectionLabel

/** Contacts / Campaigns: protocol 1.0 has no device-side contacts or campaign API, so nothing is listed here. */
@Composable
fun ManagedOnPcScreen(title: Int, body: Int) {
    val core = LocalContext.current.core()
    val connection by core.socket.state.collectAsStateWithLifecycle()
    Column(modifier = Modifier.fillMaxSize()) {
        AppHeader(stringResource(title), stringResource(R.string.managed_on_pc))
        SectionCard(stringResource(R.string.managed_on_pc)) {
            val (chip, tone) = connectionChip(connection)
            StatusChip(chip, tone)
            MutedText(stringResource(body))
            val (label, t) = connectionLabel(connection)
            KeyValueRow(stringResource(R.string.pairing_state), label, t)
        }
    }
}
