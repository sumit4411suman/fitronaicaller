package com.fitron.sellagent.audiotest.ui

import android.content.Context
import com.fitron.sellagent.R
import com.fitron.sellagent.audiotest.RunState
import com.fitron.sellagent.audiotest.TestPlan
import com.fitron.sellagent.core.AppInfo
import com.fitron.sellagent.protocol.PROTOCOL_VERSION
import com.fitron.sellagent.protocol.ProtocolJson
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** Builds the shareable report (plain text and JSON). Both carry the mandatory evidence banner. */
object ReportBuilder {

    fun text(context: Context, run: RunState, networkNote: String): String {
        val sb = StringBuilder()
        sb.appendLine("SELL AGENT - AUDIO FEASIBILITY TEST REPORT")
        sb.appendLine("==========================================")
        sb.appendLine(context.getString(R.string.report_banner))
        sb.appendLine()
        sb.appendLine("Test ID        : ${run.testId ?: "-"}")
        sb.appendLine("Started (UTC)  : ${run.startedAt ?: "-"}")
        sb.appendLine("Device         : ${AppInfo.deviceModel()}")
        sb.appendLine("Android        : ${AppInfo.androidVersion()}")
        sb.appendLine("App version    : ${AppInfo.appVersion(context)} (protocol $PROTOCOL_VERSION)")
        sb.appendLine("Network config : ${networkNote.ifBlank { "(not entered)" }}")
        sb.appendLine()
        TestPlan.steps.forEachIndexed { i, step ->
            val r = run.records.firstOrNull { it.step == step.step }
            sb.appendLine("${i + 1}. ${step.step} [${step.direction}] -> ${r?.status ?: "not_tested"}${if (r?.sent == true) " (sent)" else ""}")
            sb.appendLine("   ${context.getString(step.title)}")
            if (r != null) {
                r.apiUsed?.let { sb.appendLine("   api_used: $it") }
                r.route?.let { sb.appendLine("   route: $it") }
                r.errorMessage?.let { sb.appendLine("   error: $it") }
                if (r.observation.isNotBlank()) sb.appendLine("   observation: ${r.observation}")
                r.metrics.forEach { (k, v) -> sb.appendLine("   $k = $v") }
                r.evidence.filterKeys { it != "operator_observation" }.forEach { (k, v) -> sb.appendLine("   $k: $v") }
                r.occurredAt?.let { sb.appendLine("   at: $it") }
            }
        }
        sb.appendLine()
        sb.appendLine("Timeline:")
        run.timeline.takeLast(150).forEach { sb.appendLine("  $it") }
        sb.appendLine()
        sb.appendLine(context.getString(R.string.report_banner))
        return sb.toString()
    }

    fun json(context: Context, run: RunState, networkNote: String): String {
        val obj: JsonObject = buildJsonObject {
            put("report", "sellagent_audio_feasibility")
            put("banner", context.getString(R.string.report_banner))
            put("protocol_version", PROTOCOL_VERSION)
            put("test_id", run.testId)
            put("started_at", run.startedAt)
            put("device_model", AppInfo.deviceModel())
            put("android_version", AppInfo.androidVersion())
            put("app_version", AppInfo.appVersion(context))
            put("network_config", networkNote)
            put("kind", "real_device_app_report")
            val steps: JsonArray = buildJsonArray {
                TestPlan.steps.forEach { step ->
                    val r = run.records.firstOrNull { it.step == step.step }
                    add(
                        buildJsonObject {
                            put("step", step.step)
                            put("direction", step.direction)
                            put("status", r?.status ?: "not_tested")
                            put("sent", r?.sent ?: false)
                            put("api_used", r?.apiUsed)
                            put("route", r?.route)
                            put("error_message", r?.errorMessage)
                            put("observation", r?.observation ?: "")
                            put("occurred_at", r?.occurredAt)
                            put("metrics", JsonObject((r?.metrics ?: emptyMap()).mapValues { JsonPrimitive(it.value) }))
                            put("evidence", JsonObject((r?.evidence ?: emptyMap()).mapValues { JsonPrimitive(it.value) }))
                        },
                    )
                }
            }
            put("steps", steps)
            put("timeline", JsonArray(run.timeline.takeLast(300).map { JsonPrimitive(it) }))
        }
        return ProtocolJson.encodeToString(JsonObject.serializer(), obj)
    }
}
