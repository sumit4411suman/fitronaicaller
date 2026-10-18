# FITRONAICALLER: direct Jio call-audio feasibility report and go/no-go

Status date: 2026-10-18. Device: Samsung Galaxy S25 (SM-S931B), Android 17 (SDK 37), Jio SIM, Wi-Fi Calling.

**Decision: NO-GO for direct AI calling on the Jio number from a third-party Android app.** Criteria 2 and 3 of the
go/no-go gate (digital call audio in both directions) cannot be met through public Android APIs. They need privileged
system access, an authorised Samsung OEM integration or a documented Jio carrier interface, and none of these is
available to this project. In line with the specification, no SIP number and no acoustic speaker-to-microphone relay is
used as a substitute. Development continues on everything that does not depend on that audio path.

**Galaxy S25 specifically: still NO-GO (2026-10-18 re-confirmation).** The S25 cannot be made a privileged app
without rooting, and One UI 8 removed the OEM-unlocking path, so rooting is not available either. Full audit:
`docs/S25_COMPATIBILITY.md`. The two rooted-phone projects re-evaluated (AgentCall, GSM2SIP) both require Magisk
root and a Qualcomm `incall_music` path and both mark Samsung Exynos "no path"; neither supports the S25.

**Recommended path for autonomous calling that keeps the Jio number: a separate, qualified USB cellular modem +
Asterisk (not the S25), feeding SELL AGENT's local AI over the AudioSocket media gateway** — open-source, local,
no paid API. It is a *candidate*, gated on one unproven fact: that the modem does **VoLTE voice on Jio with USB
audio**, which must be verified **before any purchase** (`docs/JIO_MODEM_FEASIBILITY.md`,
`docs/CALLING_ARCHITECTURE.md`, `docs/TELEPHONY_BRIDGE_EVALUATION.md`). The software seam is implemented and
tested with simulated audio (`telecom/media_gateway.py`, `telecom/audiosocket.py`) and stays behind the
real-device evidence gate.

## 1. Feasibility tests A-G

The diagnostic app (`apps/android-audio-diagnostic`, 18-step plan) records each step on the S25 and sends it to the PC,
where the operator confirms it.

On 2026-10-18 the operator ran the earlier 16-step build and marked every step Pass on the phone. None of those rows
were operator-confirmed on the PC. Step 4 had no proof that call audio opened, and step 5 played speech through the
loudspeaker, which is an acoustic relay. Neither counts as digital evidence, so both are listed below as UNVERIFIED or
expected BLOCKED until rerun with this build.

| # | Feature | Test method (app step) | Expected from documented APIs | Actual result | Status | Evidence / access needed |
|---|---|---|---|---|---|---|
| A | Initiate a permitted call | `outgoing_call`: TelecomManager.placeCall from the Call tab, to a consenting test number | Works with CALL_PHONE; the default-dialer role gives full InCallService control | Operator observed the call ring and connect (2026-10-18), not yet confirmed on the PC | UNVERIFIED (observed, unconfirmed) | Public API. Confirm the row on the PC to make it PASS |
| B | Legitimate call-state information | `call_state_reporting`: TelephonyCallback + InCallService Call.Callback timeline | Dialing/ringing/active/disconnected available; detailed states need the default-dialer role | Operator observed state events; default-dialer role granted after "Allow restricted settings" | UNVERIFIED (observed, unconfirmed) | Public API (ROLE_DIALER) |
| C | Remote party's digital audio during a Jio Wi-Fi call | `remote_speech_capture`: AudioRecord probe of VOICE_DOWNLINK / VOICE_CALL / VOICE_UPLINK | Fails: these sources need CAPTURE_AUDIO_OUTPUT (signature\|privileged). InCallService gives route control, not the stream | Marked Pass on the phone, but no probe evidence that a call-audio source opened; the PC refuses to confirm it (`remote_capture_unproven`) | Expected BLOCKED (rerun to record) | Requires a system/OEM-signed app or carrier support |
| D | Inject generated audio into the call | `generated_speech_transmission` | No public API puts app audio into a cellular/IMS uplink. The app's TTS test is acoustic and never counts | Marked Pass, but via loudspeaker (acoustic relay), which is prohibited as evidence; the PC refuses (`digital_injection_unproven`) | Expected BLOCKED (rerun to record) | Requires privileged telephony/audio HAL access or OEM/carrier interface |
| E | Both directions together, low latency | `simultaneous_two_way`, `latency_echo_quality` | Depends on C and D | Cannot pass while C and D are blocked; "both" steps never open the gate | BLOCKED by C/D | n/a |
| F | Support via public API, authorised OEM or carrier interface | `platform_api_support` (new): records CAPTURE_AUDIO_OUTPUT, MODIFY_PHONE_STATE, RECORD_AUDIO, CALL_PHONE, default-dialer, InCallService binding | CAPTURE_AUDIO_OUTPUT and MODIFY_PHONE_STATE denied to a Play/sideloaded app; no public stream API | Not run yet (new step in this build) | UNVERIFIED (expected BLOCKED) | No public API. Samsung or Jio would have to provide and authorise a supported interface; none is known to be offered for this use |
| G | Keep the existing Jio number for outbound and inbound | `jio_number_retention` (new): caller-ID check on an outbound call, plus an inbound call to the S25 | Outbound caller ID and inbound delivery stay on the SIM; this is ordinary telephony | Not run yet | UNVERIFIED | Operator observation. Commercial use of a personal number for promotional calls is restricted by TRAI (see COMPLIANCE_INDIA.md) |

To mark a row PASS, run the step on the S25 with this build, then confirm it in **Devices > Audio feasibility console**.
The PC enforces the evidence rules: inbound needs `remote_capture_possible = true`, outbound needs
`uplink_injection = digital`, and no acoustic path is accepted.

## 2. Go/no-go gate (specification section 4)

| Criterion | Met? |
|---|---|
| 1. Real Jio call established | Observed (A), awaiting confirmation |
| 2. Remote voice reaches the AI through a verified digital input | **No** (C blocked) |
| 3. AI speech reaches the remote party through a verified digital output | **No** (D blocked) |
| 4. No acoustic relay involved | Enforced in code; the acoustic bridge was removed |
| 5. Both directions over multiple turns | **No** (depends on 2 and 3) |
| 6. Termination, interruption, routing, recovery | Termination and routing via InCallService are testable; audio parts blocked |
| 7. Calling method supported by carrier and platform | **No** supported interface found |

`release_gate.autonomous_calling_allowed` stays false, autonomous campaigns cannot be created, and the Call Console
shows that AI telephone calling is unavailable.

## 3. Blocker report

- **What blocks:** Android restricts call-audio capture (`CAPTURE_AUDIO_OUTPUT`) and in-call audio injection to
  system or privileged apps signed with the platform key. A retail Galaxy S25 cannot grant this to a third-party app
  without rooting or unlocking, which is prohibited.
- **What would unblock it legitimately:**
  1. A written Samsung OEM integration that installs a privileged component for this purpose.
  2. A documented Jio carrier interface that exposes call media for the subscriber's own number.
  We know of no public offering of either for this use. The project owner would need to ask Samsung and Jio directly.
- **What is explicitly not done:** no root; no undocumented APIs; no accessibility-service tricks; no SIP or other
  replacement number; no speaker-to-microphone relay. The acoustic bridge merged in an earlier PR was removed in this
  change because the specification prohibits it.

## 4. What continues (independent of the blocker)

| Area | Implemented | Tested here | Remaining / unverified |
|---|---|---|---|
| Android feasibility app (18 device steps incl. F, G; backend plan adds 5 full-loop steps = 23) | Yes | CI build | Real S25 rerun of all steps |
| Android companion (pairing, call control, state, routing, emergency stop) | Yes | CI build; pairing and call states observed by operator | Formal confirmation rows |
| Local voice pipeline: VAD (Silero v6 or energy) -> faster-whisper -> conversation engine -> Piper, with stage timings, cancellation, barge-in detection, audio validation | Yes (`sellagent_speech/pipeline.py`, `POST /speech/pipeline-test`) | Unit and API tests with fake models; real Silero model tested | Real Whisper/Piper runs on the Windows PC (`tests/voice`, opt-in); no measured WER/latency yet |
| Hindi / English voice suite | Yes (`tests/voice`) | Skips without models | Run on the PC with models and consenting recordings |
| Autonomous conversation loop (`sellagent_backend/autonomy`): barge-in, language following, silence and poor-recognition fallback, opt-out, emergency stop | Yes, but it runs only on a verified digital call-audio path; real routes return none | Simulated path tests | Needs a verified path, which does not exist for Android/Jio |
| Modular audio gateway + Asterisk AudioSocket server (`telecom/media_gateway.py`, `telecom/audiosocket.py`): documented `MediaTransport`, PCM path with bounded jitter buffer/backpressure, loopback-only, fail-closed gate, `media_gateway` route | Yes | `tests/integration/test_media_gateway.py`, `test_audiosocket.py` (simulated audio, wire protocol, gating, full conversation) | Real modem + Asterisk + a verified Jio VoLTE route; see JIO_MODEM_FEASIBILITY |
| AI sales persona (female "Priya", Hindi feminine forms, cue-aware replies, call memory, voice pacing) | Yes (`docs/PERSONA.md`) | Unit, API and UI tests in script mode | Voice naturalness and latency on the real PC; LLM-mode quality |
| Conversation engine, guardrails, opt-out, consent, eligibility, CRM, campaigns, reports | Yes | Automated tests (see TEST_REPORT.md) | Human-assisted use only |
| Secure Windows-Android link (pairing code + TLS fingerprint pinning, authenticated WebSocket) | Yes | Automated tests; real pairing observed on the S25 | n/a |

## 5. Known issue found while writing this report

`LICENSES/README.md` records the decision to run Piper (GPL-3.0) as a separate process for the proprietary build, but
`sellagent_speech/tts.py` imports `piper` in-process. Before distributing a build that includes Piper, either switch
`PiperTTS` to a subprocess interface or confirm the licensing approach.
