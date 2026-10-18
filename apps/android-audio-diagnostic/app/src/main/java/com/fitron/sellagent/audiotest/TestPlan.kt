package com.fitron.sellagent.audiotest

import androidx.annotation.StringRes
import com.fitron.sellagent.R
import com.fitron.sellagent.protocol.AudioDirection

/** One entry of the backend TEST_PLAN (services/local-backend/.../audio_tests.py). `step` ids must match exactly. */
data class TestStep(
    val step: String,
    val direction: String,
    @StringRes val title: Int,
    @StringRes val instruction: Int,
    val tool: StepTool,
)

/** Which automatic measurement the Test Runner offers for a step. */
enum class StepTool { NONE, CONNECTION, CALL_STATE, DIAL, REMOTE_CAPTURE, TTS, TWO_WAY, ROUTE_EARPIECE, ROUTE_SPEAKER, ROUTE_BLUETOOTH, ROUTE_WIRED, LOOPBACK, SCREEN_LOCK, WIFI_DROP, TTS_HINDI, TTS_ENGLISH, VOWIFI, API_SUPPORT }

object TestPlan {
    val steps: List<TestStep> = listOf(
        TestStep("pairing", AudioDirection.NONE, R.string.step_pairing, R.string.ins_pairing, StepTool.CONNECTION),
        TestStep("call_state_reporting", AudioDirection.NONE, R.string.step_call_state_reporting, R.string.ins_call_state_reporting, StepTool.CALL_STATE),
        TestStep("outgoing_call", AudioDirection.NONE, R.string.step_outgoing_call, R.string.ins_outgoing_call, StepTool.DIAL),
        TestStep("remote_speech_capture", AudioDirection.INBOUND, R.string.step_remote_speech_capture, R.string.ins_remote_speech_capture, StepTool.REMOTE_CAPTURE),
        TestStep("generated_speech_transmission", AudioDirection.OUTBOUND, R.string.step_generated_speech_transmission, R.string.ins_generated_speech_transmission, StepTool.TTS),
        TestStep("simultaneous_two_way", AudioDirection.BOTH, R.string.step_simultaneous_two_way, R.string.ins_simultaneous_two_way, StepTool.TWO_WAY),
        TestStep("route_earpiece", AudioDirection.NONE, R.string.step_route_earpiece, R.string.ins_route_earpiece, StepTool.ROUTE_EARPIECE),
        TestStep("route_speaker", AudioDirection.NONE, R.string.step_route_speaker, R.string.ins_route_speaker, StepTool.ROUTE_SPEAKER),
        TestStep("route_bluetooth", AudioDirection.NONE, R.string.step_route_bluetooth, R.string.ins_route_bluetooth, StepTool.ROUTE_BLUETOOTH),
        TestStep("route_wired", AudioDirection.NONE, R.string.step_route_wired, R.string.ins_route_wired, StepTool.ROUTE_WIRED),
        TestStep("latency_echo_quality", AudioDirection.BOTH, R.string.step_latency_echo_quality, R.string.ins_latency_echo_quality, StepTool.LOOPBACK),
        TestStep("screen_locked", AudioDirection.NONE, R.string.step_screen_locked, R.string.ins_screen_locked, StepTool.SCREEN_LOCK),
        TestStep("wifi_interruption", AudioDirection.NONE, R.string.step_wifi_interruption, R.string.ins_wifi_interruption, StepTool.WIFI_DROP),
        TestStep("hindi_phrases", AudioDirection.BOTH, R.string.step_hindi_phrases, R.string.ins_hindi_phrases, StepTool.TTS_HINDI),
        TestStep("english_phrases", AudioDirection.BOTH, R.string.step_english_phrases, R.string.ins_english_phrases, StepTool.TTS_ENGLISH),
        TestStep("jio_wifi_calling", AudioDirection.NONE, R.string.step_jio_wifi_calling, R.string.ins_jio_wifi_calling, StepTool.VOWIFI),
        TestStep("platform_api_support", AudioDirection.NONE, R.string.step_platform_api_support, R.string.ins_platform_api_support, StepTool.API_SUPPORT),
        TestStep("jio_number_retention", AudioDirection.NONE, R.string.step_jio_number_retention, R.string.ins_jio_number_retention, StepTool.NONE),
    )

    fun byId(step: String): TestStep? = steps.firstOrNull { it.step == step }

    /** Fixed phrases spoken by TTS. Kept in code (not translated) because they ARE the test material. */
    val hindiPhrases: List<String> = listOf(
        "नमस्ते, मैं फ़िट्रॉन की ओर से बोल रहा हूँ। क्या आप मुझे साफ़ सुन पा रहे हैं?",
        "कृपया एक से दस तक गिनें और बताएं कि आवाज़ कहाँ कटती है।",
        "यह एक परीक्षण कॉल है। किसी भी जानकारी की आवश्यकता नहीं है।",
    )
    val englishPhrases: List<String> = listOf(
        "Hello, this is a test call from FITRON. Can you hear me clearly?",
        "Please count from one to ten and tell me where the audio breaks.",
        "This is a test call. No information is required from you.",
    )
}
