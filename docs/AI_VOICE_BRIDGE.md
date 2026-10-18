# AI voice bridge (experimental, operator-supervised)

## What it is

Android does not give normal apps the other person's voice on a SIM call (see `TELECOM_FEASIBILITY.md` §2). The bridge works around this **acoustically, with no hidden APIs and no root**:

- The Galaxy S25 stays on the call on **speakerphone**, placed next to the PC.
- The **PC speaker** plays the AI's voice (Piper TTS). The phone's microphone picks it up and sends it into the call.
- The **PC microphone** hears the prospect through the phone's loudspeaker. faster-whisper turns it into text locally.
- The normal conversation engine decides what to say next. It uses the same state machine, approved knowledge, price guardrails and opt-out handling as the Call Console.

Audio stays in memory and is never saved; only the text lines are stored. Everything runs offline after the models are installed.

## What it is not

- **Not autonomous.** The operator starts it on each call they are watching, and can press **Take over** or **EMERGENCY STOP** at any moment. Nothing dials by itself.
- **Not evidence for the release gate.** A bridge call is recorded as an `acoustic_bridge_call` row in the Audio feasibility console so you can judge it. It does **not** open `release_gate.autonomous_calling_allowed`, which still needs steps 4 and 5 proven on the phone itself.
- **Not tested on real calls yet.** The logic is tested with scripted replies (`tests/integration/test_ai_bridge.py`), which say nothing about audio quality. Expect room echo, background noise and a 1–3 s delay per reply on a CPU-only PC. The bridge is half-duplex: the AI cannot be interrupted while it speaks.

## Rules it enforces

| Check | Where |
|---|---|
| `bridge.enabled` must be on (default **off**) | preflight |
| `privacy.allow_live_transcription` must be on | preflight |
| Call must be live (operator pressed **Connected**) | preflight and every turn |
| Contact not opted out; consent `granted` when `calling.require_consent` | preflight |
| One AI call at a time | preflight |
| First words: "automated AI assistant", plus a request for consent to convert speech to text | session |
| Continues only after a clear **yes**. "No" ends politely; "do not call" opts the contact out; "talk to a person" ends with a human callback | session |
| Silence: asks once more, then ends the call politely | session |
| Emergency stop or operator take-over stops audio immediately | manager and every turn |

## How to use

1. Install the speech stack and models (`requirements-speech.txt`, `models/README.md`). For Hindi, set a Hindi Piper voice in `ai.piper_voice_hi`.
2. In **Settings**, turn on `bridge.enabled` and `privacy.allow_live_transcription`. If the wrong devices are used, set `bridge.input_device` and `bridge.output_device` (device index or name; see **Diagnostics > audio devices**).
3. Start a call as usual, put the phone on **speakerphone** next to the PC, and press **Connected** when the person answers.
4. On the Call Console, press **Let AI talk**. Watch the transcript, and press **Take over** to speak yourself.
5. If the AI cannot hear the prospect, raise `bridge.mic_threshold_db` (more sensitive) or move the phone closer. If it hears room noise as speech, lower it.

## Settings

| Key | Default | Meaning |
|---|---|---|
| `bridge.enabled` | false | master switch |
| `bridge.max_turns` | 14 | AI turns before it wraps up |
| `bridge.listen_timeout_s` | 8 | wait for the prospect to start speaking |
| `bridge.max_utterance_s` | 15 | longest single reply recorded |
| `bridge.max_silences` | 2 | silent waits before ending politely |
| `bridge.mic_threshold_db` | 42 | speech detection threshold, -42 dBFS (higher = more sensitive) |
| `bridge.input_device` / `bridge.output_device` | "" | PortAudio device (empty = Windows default) |

## Compliance

Use the bridge only for people who agreed to be called (leads who asked for a callback, existing members, trial sign-ups). The AI always identifies itself and stops on request. Automated promotional calling to people who have not consented needs a registered telemarketer route under TRAI rules (see `COMPLIANCE_INDIA.md`).
