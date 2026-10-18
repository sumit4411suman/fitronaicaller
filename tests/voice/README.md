# Hindi / English voice test suite (opt-in, real local models)

Runs the real local pipeline (Silero VAD -> faster-whisper -> Piper) on the Windows PC, **separately for Hindi and
English**, and writes a JSON report with word error rate (WER) and per-stage latency to `<data>/reports/voice/`.

```powershell
$env:SELLAGENT_VOICE_TESTS = "1"
$env:SELLAGENT_MODELS_DIR  = "C:\SellAgent\models"     # whisper + piper/<voice>.onnx(.json)
$env:SELLAGENT_VOICE_EN    = "en_US-lessac-medium"      # Piper voice names
$env:SELLAGENT_VOICE_HI    = "hi_IN-pratham-medium"
$env:SELLAGENT_WHISPER     = "small"                    # base is weak for Hindi
python -m pytest tests/voice -m model -q
```

Two kinds of input:

1. **Synthetic**: fixed phrases spoken by Piper, then transcribed. These measure the pipeline and latency, but
   machine speech is easier than real callers.
2. **Recorded human speech** (recommended): put 16-bit PCM WAV files in `tests/voice/audio/en/` and
   `tests/voice/audio/hi/`, each with a same-named `.txt` file holding the exact words. Record consenting speakers only.
   The files stay on your PC; `.gitignore` keeps them out of the repository.

None of this involves the phone or a cellular call. It is not evidence of call-audio access.
