package com.fitron.sellagent.audiotest

import android.content.Context
import com.fitron.sellagent.core.AppInfo
import com.fitron.sellagent.core.CoreContainer
import com.fitron.sellagent.core.net.ConnectionState
import com.fitron.sellagent.core.telecom.AudioRouting
import com.fitron.sellagent.core.telecom.CallMonitor
import com.fitron.sellagent.core.telecom.SellAgentInCallService
import com.fitron.sellagent.protocol.AudioTestEvent
import com.fitron.sellagent.protocol.AudioTestResult
import com.fitron.sellagent.protocol.EmergencyStop
import com.fitron.sellagent.protocol.Envelope
import com.fitron.sellagent.protocol.MessageType
import com.fitron.sellagent.protocol.ProtocolJson
import com.fitron.sellagent.protocol.TestStatus
import com.fitron.sellagent.protocol.nowIso
import java.io.File
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.Serializable

@Serializable
data class StepRecord(
    val step: String,
    val status: String = TestStatus.NOT_TESTED,
    val observation: String = "",
    val apiUsed: String? = null,
    val route: String? = null,
    val errorMessage: String? = null,
    val metrics: Map<String, Double> = emptyMap(),
    val evidence: Map<String, String> = emptyMap(),
    val occurredAt: String? = null,
    val sent: Boolean = false,
)

@Serializable
data class RunState(
    val testId: String? = null,
    val startedAt: String? = null,
    val records: List<StepRecord> = emptyList(),
    val timeline: List<String> = emptyList(),
)

/**
 * In-memory + file-backed state of one Audio Feasibility Test run. Survives rotation (lives in the Application) and
 * process death (persisted to files/aft_run.json after every change). Every step result is sent as
 * `audio_test.result`; intermediate observations go out as `audio_test.event`.
 */
class TestSession(context: Context, private val core: CoreContainer) {
    private val file = File(context.filesDir, "aft_run.json")
    private val _run = MutableStateFlow(load())
    val run: StateFlow<RunState> = _run

    /** Counters used by the screen-lock and Wi-Fi-drop steps. */
    private val _heartbeatAcks = MutableStateFlow(0)
    val heartbeatAcks: StateFlow<Int> = _heartbeatAcks
    private val _reconnects = MutableStateFlow(0)
    val reconnects: StateFlow<Int> = _reconnects
    private val _maxBackoff = MutableStateFlow(0)
    val maxBackoff: StateFlow<Int> = _maxBackoff
    private val _disconnects = MutableStateFlow(0)
    val disconnects: StateFlow<Int> = _disconnects

    init {
        core.scope.launch { core.callMonitor.events.collect { note("TelephonyCallback ${CallMonitor.describe(it.telephonyState)} -> ${it.protocolState}") } }
        core.scope.launch {
            SellAgentInCallService.events.collect {
                note("InCallService ${SellAgentInCallService.describeState(it.telecomState)} -> ${it.protocolState} route=${it.audioRoute}${it.disconnectCause?.let { c -> " cause=$c" } ?: ""}")
            }
        }
        core.scope.launch {
            var wasConnected = false
            core.socket.state.collect { st ->
                when (st) {
                    is ConnectionState.Connected -> {
                        if (!wasConnected) _reconnects.value = _reconnects.value + 1
                        wasConnected = true
                        note("socket connected")
                    }
                    is ConnectionState.Backoff -> {
                        if (wasConnected) _disconnects.value = _disconnects.value + 1
                        wasConnected = false
                        if (st.retryInSeconds > _maxBackoff.value) _maxBackoff.value = st.retryInSeconds
                        note("socket backoff ${st.retryInSeconds}s: ${st.reason.take(60)}")
                    }
                    else -> Unit
                }
            }
        }
        core.scope.launch {
            core.socket.lastHeartbeatAckAt.collect { if (it != null) _heartbeatAcks.value = _heartbeatAcks.value + 1 }
        }
    }

    val testId: String? get() = _run.value.testId

    fun startRun() {
        val id = "AFT-" + LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd-HHmm"))
        _run.value = RunState(testId = id, startedAt = nowIso(), records = TestPlan.steps.map { StepRecord(it.step) }, timeline = emptyList())
        _heartbeatAcks.value = 0
        _reconnects.value = 0
        _maxBackoff.value = 0
        _disconnects.value = 0
        persist()
        note("run $id started on ${AppInfo.deviceModel()} ${AppInfo.androidVersion()}")
    }

    fun record(step: String): StepRecord = _run.value.records.firstOrNull { it.step == step } ?: StepRecord(step)

    fun setObservation(step: String, text: String) = update(step) { it.copy(observation = text) }

    /** Store the result locally and send it as audio_test.result (durable; replayed after reconnect). */
    fun finish(
        step: String,
        status: String,
        apiUsed: String? = null,
        route: String? = null,
        errorMessage: String? = null,
        metrics: Map<String, Double> = emptyMap(),
        evidence: Map<String, String> = emptyMap(),
    ) {
        val id = testId ?: return
        val def = TestPlan.byId(step) ?: return
        val current = record(step)
        val mergedEvidence = (current.evidence + evidence).toMutableMap()
        if (current.observation.isNotBlank()) mergedEvidence["operator_observation"] = current.observation.take(500)
        mergedEvidence["device"] = AppInfo.deviceModel()
        mergedEvidence["android"] = AppInfo.androidVersion()
        mergedEvidence["kind"] = "real_device_app_report"
        val mergedMetrics = current.metrics + metrics
        val result = AudioTestResult(
            testId = id,
            step = step,
            direction = def.direction,
            status = status,
            route = route ?: AudioRouting.currentRoute(core.app),
            apiUsed = apiUsed ?: current.apiUsed,
            errorMessage = errorMessage ?: current.errorMessage,
            metrics = mergedMetrics,
            evidence = mergedEvidence,
        )
        core.socket.send(Envelope.of(MessageType.AUDIO_TEST_RESULT, result, AudioTestResult.serializer()), durable = true)
        update(step) {
            it.copy(
                status = status, apiUsed = result.apiUsed, route = result.route, errorMessage = result.errorMessage,
                metrics = mergedMetrics, evidence = mergedEvidence, occurredAt = result.occurredAt, sent = true,
            )
        }
        note("result $step=$status${result.apiUsed?.let { a -> " via $a" } ?: ""}")
    }

    /** Attach a measurement to a step without finishing it, and stream it as audio_test.event. */
    fun measure(step: String, apiUsed: String?, metrics: Map<String, Double>, evidence: Map<String, String>, message: String, levelDbfs: Double? = null, latencyMs: Double? = null) {
        update(step) { it.copy(apiUsed = apiUsed ?: it.apiUsed, metrics = it.metrics + metrics, evidence = it.evidence + evidence) }
        val id = testId ?: return
        val def = TestPlan.byId(step) ?: return
        val ev = AudioTestEvent(testId = id, step = step, direction = def.direction, route = AudioRouting.currentRoute(core.app), levelDbfs = levelDbfs, latencyMs = latencyMs, message = message.take(500))
        core.socket.send(Envelope.of(MessageType.AUDIO_TEST_EVENT, ev, AudioTestEvent.serializer()), durable = false)
        note("$step: $message")
    }

    fun note(line: String) {
        val stamp = java.time.LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm:ss"))
        _run.value = _run.value.copy(timeline = (_run.value.timeline + "$stamp $line").takeLast(400))
        persist()
    }

    fun emergencyStop(reason: String) {
        core.socket.latchEmergencyStop()
        core.socket.send(Envelope.of(MessageType.EMERGENCY_STOP, EmergencyStop(reason = reason, issuedBy = "android"), EmergencyStop.serializer()), durable = true)
        val ended = SellAgentInCallService.endActiveCall()
        note("EMERGENCY STOP sent ($reason); call ended via InCallService=$ended")
    }

    private fun update(step: String, f: (StepRecord) -> StepRecord) {
        val recs = _run.value.records.toMutableList()
        val idx = recs.indexOfFirst { it.step == step }
        if (idx >= 0) recs[idx] = f(recs[idx]) else recs.add(f(StepRecord(step)))
        _run.value = _run.value.copy(records = recs)
        persist()
    }

    private fun persist() {
        runCatching { file.writeText(ProtocolJson.encodeToString(RunState.serializer(), _run.value)) }
    }

    private fun load(): RunState = runCatching {
        if (file.exists()) ProtocolJson.decodeFromString(RunState.serializer(), file.readText()) else RunState()
    }.getOrDefault(RunState())
}
