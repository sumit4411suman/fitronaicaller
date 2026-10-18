# AI sales persona

The persona is the voice and personality of the SELL AGENT conversation engine. It is configured on **AI Settings > AI sales persona**, with the same keys also on **Settings** under `persona.*`. The default persona is "Priya": female, warm, short replies, follows the caller between Hindi and English.

## What it does

| Capability | How | Where |
|---|---|---|
| Identifies as an AI, never as a human | The default greeting says "I'm Priya, an automated AI assistant...". A custom greeting without "AI" gets the disclosure added automatically. The LLM prompt forbids claiming to be human or having feelings. | `sellagent_ai/persona.py`, `conversation/engine.py` |
| Feminine Hindi | The approved Hindi lines are converted to feminine first-person forms ("बोल रही हूँ", "समझ गई", "करवाती हूँ"); the LLM is told to do the same | `scripts.gendered` |
| Responds to what the owner says | Cues are inferred from the **words** the owner used, not from voice tone. They are hints only, never treated as facts: busy, confused / asks to repeat, price concern, already uses software, interest, hesitation, impatience, ending the call | `infer_cues` |
| Busy owner | Short call-back offer instead of a pitch, then follow-up scheduling | engine |
| Confused owner | Says the same thing more simply, staying at the same step | `scripts.SIMPLER` |
| Already uses software | Asks what they would like to improve, then continues. It never names tools like Tally, because the guardrails treat that as an integration claim | engine + guardrails |
| Ends the call ("ok thank you bye") | Polite close; the outcome is saved | engine |
| Interest / hesitation / impatience | Short acknowledgement ("Great.", "No pressure at all.", "I'll be quick.") | `scripts.ACKS` |
| No word-for-word repetition | Uses an alternative wording if the line equals the previous one | `scripts.ALTERNATIVES` |
| Memory of the current call | Rebuilt from the call's own transcript each turn: last N turns, the tool they use, needs mentioned (membership, payments, accounting). Nothing carries over between calls | `ConversationMemory`, `services/persona_service.py` |
| LLM rephrasing (optional) | Persona style, call history, memory summary and cues go into the prompt. Every reply still passes the guardrails, and any rejected reply falls back to the approved script line | engine |
| Voice | Piper voice per language, speed (`ai.tts_speed_percent`), volume, pause after each sentence | `PiperTTS.synthesize` |
| Interruptions | With `persona.barge_in`, the AI stops speaking as soon as the caller talks, on a verified call-audio path | `autonomy/runner.py` |
| Asking for a person | `callback`: the AI arranges a human call-back. `operator`: the live call is handed to the operator immediately | runner |

## What it cannot change

Approved facts and prices, guardrails, consent, opt-out, suppression, quiet hours, privacy settings and the emergency stop are enforced by the backend and the state machine before or after the persona. Tests cover this:
- An opt-out phrase wins even when "busy" is also said.
- An invented price in a custom greeting is replaced.
- Emergency stop silences the persona.

## Real phone calls

The persona speaks through the conversation engine everywhere: in the Call Console line suggestions (human-assisted), the rehearsal simulator and the PC voice-pipeline test. It speaks **directly to a gym owner on a live call only** through the autonomous loop. That loop runs only on a verified digital call-audio path, and the S25/Jio route has none (`docs/FEASIBILITY_REPORT.md`). No acoustic speaker-to-microphone relay is used.

## Voice evaluation

Real-PC measurements of naturalness, pronunciation and latency are **not done yet**: voice models could not be downloaded in the build environment. Run them on the target PC with **Persona > Preview voice**, which shows the generation time, and with `tests/voice` (WER and latency per language).

| Option | Female | Hindi | English accent | Code-switching | Licence | Status |
|---|---|---|---|---|---|---|
| Piper `hi_IN-priyamvada-medium` | yes | yes | n/a | Roman-script English words may be mispronounced | per-voice dataset licence: **check MODEL_CARD before commercial use** | recommended Hindi voice, unmeasured |
| Piper `en_US-lessac-medium` / `en_US-amy-medium` | yes | no | US English | n/a | per-voice: check MODEL_CARD | default English voice, unmeasured |
| Piper Indian-English female voice | none known in the rhasspy/piper-voices catalogue at the time of writing | | | | | gap: English is spoken with a US accent |
| MMS-TTS (Meta) | n/a | yes | | | CC-BY-NC 4.0, **non-commercial** | excluded |
| Cloud voices (Google, Azure, ElevenLabs...) | yes | yes | Indian English available | better | paid, cloud | not used; would need explicit opt-in |

Piper voices are single-language. A sentence that mixes Hindi and English is spoken by one voice, so code-switched speech will sound less natural than a human. Piper is a local neural TTS: expect clear but noticeably synthetic speech, not a human-level voice.

## Settings

| Key | Default | Notes |
|---|---|---|
| `persona.enabled` | true | off = original neutral script lines |
| `persona.name` | Priya | 1-40 characters |
| `persona.gender` | female | Hindi verb agreement |
| `persona.style` | warm | warm / concise / formal (LLM wording) |
| `persona.response_length` | short | short / normal (LLM wording) |
| `persona.default_language`, `persona.language_switching` | auto, true | with switching off, the persona keeps its default language |
| `persona.voice_en`, `persona.voice_hi` | "" | empty = `ai.piper_voice_*` |
| `ai.tts_speed_percent`, `persona.volume_percent`, `persona.pause_ms` | 100, 100, 250 | 50-200, 20-150, 0-1500 |
| `persona.greeting_*`, `persona.closing_*` | "" | optional; `{name}`, `{contact_person}`, `{business_name}`; 500 characters max |
| `persona.objectives` | (text) | goes into the LLM prompt only |
| `persona.memory_turns` | 8 | 2-30 |
| `persona.barge_in` | true | |
| `persona.handoff` | callback | callback / operator |

## Tests

`tests/unit/test_persona.py`, `tests/integration/test_persona_api.py`, the persona parts of `tests/integration/test_autonomy.py` (simulated audio path) and `tests/ui/test_features.py::test_persona_screen_save_and_rehearse`. All run in script mode (no LLM), so the results are deterministic. LLM-mode quality depends on the local model and is not covered by automated tests.
