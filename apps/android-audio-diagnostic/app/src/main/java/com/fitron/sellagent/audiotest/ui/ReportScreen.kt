package com.fitron.sellagent.audiotest.ui

import android.content.Intent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fitron.sellagent.R
import com.fitron.sellagent.audiotest.DiagnosticApp
import com.fitron.sellagent.audiotest.TestPlan
import com.fitron.sellagent.brand.BrandColors
import com.fitron.sellagent.core.AppInfo
import com.fitron.sellagent.core.core
import com.fitron.sellagent.core.ui.AppHeader
import com.fitron.sellagent.core.ui.BannerCard
import com.fitron.sellagent.core.ui.GoldButton
import com.fitron.sellagent.core.ui.KeyValueRow
import com.fitron.sellagent.core.ui.LogList
import com.fitron.sellagent.core.ui.OutlineButton
import com.fitron.sellagent.core.ui.SectionCard
import com.fitron.sellagent.core.ui.Tone
import com.fitron.sellagent.protocol.PROTOCOL_VERSION

@Composable
fun ReportScreen() {
    val context = LocalContext.current
    val core = context.core()
    val session = (context.applicationContext as DiagnosticApp).session
    val run by session.run.collectAsStateWithLifecycle()
    val networkNote = core.store.networkConfigNote

    fun share(text: String, mime: String, subject: String) {
        val intent = Intent(Intent.ACTION_SEND).apply {
            type = mime
            putExtra(Intent.EXTRA_SUBJECT, subject)
            putExtra(Intent.EXTRA_TEXT, text)
        }
        runCatching { context.startActivity(Intent.createChooser(intent, subject)) }
    }

    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        AppHeader(stringResource(R.string.report_title), stringResource(R.string.report_subtitle))
        BannerCard(stringResource(R.string.report_banner), Tone.Bad)
        SectionCard(stringResource(R.string.runner_test_id)) {
            KeyValueRow(stringResource(R.string.runner_test_id), run.testId ?: "-", if (run.testId != null) Tone.Good else Tone.Neutral)
            KeyValueRow("Started", run.startedAt ?: "-", Tone.Neutral)
            KeyValueRow("Device", AppInfo.deviceModel(), Tone.Neutral)
            KeyValueRow("Android", AppInfo.androidVersion(), Tone.Neutral)
            KeyValueRow("App", "${AppInfo.appVersion(context)} / protocol $PROTOCOL_VERSION", Tone.Neutral)
            KeyValueRow("Network", networkNote.ifBlank { "-" }, Tone.Neutral)
            if (run.testId == null) Text(stringResource(R.string.report_empty), style = MaterialTheme.typography.bodySmall, color = BrandColors.TextSecondary)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                GoldButton(stringResource(R.string.report_share_text), enabled = run.testId != null) {
                    share(ReportBuilder.text(context, run, networkNote), "text/plain", "SELL AGENT AFT ${run.testId}")
                }
                OutlineButton(stringResource(R.string.report_share_json), enabled = run.testId != null) {
                    share(ReportBuilder.json(context, run, networkNote), "application/json", "SELL AGENT AFT ${run.testId}.json")
                }
            }
        }
        TestPlan.steps.forEachIndexed { i, step ->
            val r = run.records.firstOrNull { it.step == step.step }
            SectionCard("${i + 1}. ${stringResource(step.title)}") {
                KeyValueRow(step.step, statusLabel(r?.status ?: "not_tested"), statusTone(r?.status ?: "not_tested"))
                if (r != null) {
                    r.apiUsed?.let { KeyValueRow("api_used", it, Tone.Neutral) }
                    r.errorMessage?.let { KeyValueRow("error", it, Tone.Bad) }
                    if (r.observation.isNotBlank()) Text(r.observation, style = MaterialTheme.typography.bodySmall, color = BrandColors.TextPrimary)
                    r.metrics.forEach { (k, v) -> Text("$k = $v", style = MaterialTheme.typography.labelSmall, color = BrandColors.TextSecondary) }
                    r.evidence.filterKeys { it != "operator_observation" }.forEach { (k, v) -> Text("$k: $v", style = MaterialTheme.typography.labelSmall, color = BrandColors.TextSecondary) }
                }
            }
        }
        SectionCard(stringResource(R.string.report_timeline)) { LogList(run.timeline, maxLines = 60) }
        Text("", modifier = Modifier.padding(12.dp))
    }
}
