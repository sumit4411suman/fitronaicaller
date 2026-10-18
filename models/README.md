# Local models

SELL AGENT never downloads anything silently. Models live under the data directory
(`%LOCALAPPDATA%\SellAgent\models` on Windows) and are fetched only by `scripts/download_models.py --yes`
or by Ollama when you explicitly pull a model while `privacy.allow_external_network` is on.

| Component | Candidate | Approx. download | RAM while loaded (CPU) | Licence | Status |
| --- | --- | --- | --- | --- | --- |
| LLM (Ollama) | `qwen3:1.7b` | ~1.4 GB | ~2.5 GB | Apache-2.0 | default candidate, **benchmark before choosing** |
| LLM (Ollama) | `qwen3:4b` | ~2.6 GB | ~5 GB | Apache-2.0 | 3B-class alternative (Qwen2.5-3B rejected: non-commercial research licence) |
| STT (faster-whisper, int8) | `small` | ~480 MB | ~1 GB | MIT | recommended start for Hindi + English |
| STT | `medium` | ~1.5 GB | ~2.5 GB | MIT | better Hindi, slower |
| TTS (Piper) | `en_US-lessac-medium` | ~63 MB | <300 MB | per-voice MODEL_CARD | English |
| TTS (Piper) | `hi_IN-pratham-medium` / `hi_IN-priyamvada-medium` | ~63 MB each | <300 MB | per-voice MODEL_CARD | listed in piper-voices; **quality must be tested with Hindi phrases** |

Minimum disk for the default set (qwen3:1.7b + whisper small + one English voice): about 2.1 GB plus ~1 GB working space.
Minimum RAM: 16 GB total is sufficient for backend + desktop + one 1.7B/3B model + whisper small concurrently; the benchmark
script records the actual numbers on your machine.

Sizes above come from the model catalogues at the time of writing and must be confirmed by the download step, which prints
exact sizes before asking for `--yes`.

## Hindi/English quality

Language labels in a catalogue are not evidence. Run on the target PC:

```
python -m sellagent_ai.benchmark --provider ollama --models qwen3:1.7b qwen3:4b --out docs/benchmarks/llm.json
python scripts/offline_check.py          # with the network disconnected
```

and record the results in docs/TEST_REPORT.md. This session had no access to model downloads, so no benchmark numbers are claimed.

## Licence note on Piper

`piper-tts` 1.8.0 (piper1-gpl) is GPL-3.0. SELL AGENT imports it only lazily inside `sellagent_speech.tts` and it is an
optional extra; to keep the distributed desktop bundle free of GPL code, either run Piper as a separate process
(`piper.exe` from the Piper release, invoked by the backend) or use the archived MIT-licensed `rhasspy/piper` 2023.11.14-2
binary. See `LICENSES/README.md`.
