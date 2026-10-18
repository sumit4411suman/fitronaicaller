# SELL AGENT - Resource Evaluation

Research date: 2026-10-18. Target: Windows 11 x86-64, Python 3.12, CPU only, fully local. "Verified" means the page or metadata was fetched in this session; "search summary" means only a search-engine summary of the page was available; UNVERIFIED means neither.

Unreachable hosts in this session: huggingface.co, ollama.com, registry.ollama.ai, doc.qt.io, qt.io, sqlite.org, api.github.com (403). GitHub HTML pages, raw.githubusercontent.com, pypi.org and developer.android.com guides were reachable.

## LLM runtimes

| Resource | Contribution | Maintenance | Compatibility | License / attribution | Security | Local | Downloads | Limitations | DECISION |
|---|---|---|---|---|---|---|---|---|---|
| Ollama (github.com/ollama/ollama) | Local LLM server with OpenAI-compatible API; used by `sellagent_ai/llm/ollama.py` | Latest stable v0.40.6 (16 Oct 2026), v0.40.7-rc0 (18 Oct 2026); 183.7k stars (verified GitHub releases page) | Windows installer (`install.ps1`/manual); CPU fallback via llama.cpp backend; AVX2 recommended | MIT (verified). Attribution: include MIT notice if redistributed; we invoke an operator-installed binary, no redistribution | Listens on 127.0.0.1:11434 by default; keep `OLLAMA_HOST` local; model pulls need network (gated by `privacy.allow_external_network`) | yes | Models pulled via `ollama pull` | Separate background service; model format opaque to us | adopt (default provider) |
| llama.cpp (github.com/ggml-org/llama.cpp) | Direct GGUF inference, `llama-server` OpenAI-compatible; used by `sellagent_ai/llm/llamacpp.py` | Release b11717 (18 Oct 2026); ~131.5k stars (verified) | `llama-b11717-bin-win-cpu-x64.zip` prebuilt; AVX/AVX2/AVX512 | MIT (verified) | Local HTTP server; bind 127.0.0.1 | yes | GGUF files from HF (see models) | Frequent releases; API flags change | optional (fallback provider) |

## LLM models

| Resource | License | GGUF | Hindi | Size | Notes | DECISION |
|---|---|---|---|---|---|---|
| Qwen3-1.7B (Qwen/Qwen3-1.7B) | Apache-2.0: "All our open-weight models are licensed under Apache 2.0" (github.com/QwenLM/Qwen3, verified) | Qwen publishes GGUF repos (Qwen3-8B-GGUF cited on GitHub; 1.7B GGUF UNVERIFIED, HF unreachable) | Qwen3 claims "100+ languages and dialects"; Hindi not named on the GitHub page; quality on Hindi sales dialogue must be benchmarked (`sellagent_ai/benchmark.py`) | Ollama tag `qwen3:1.7b` about 1.4 GB (search summary citing registry.ollama.ai) | Thinking mode must be disabled for latency | adopt (default `qwen3:1.7b`) |
| Qwen2.5-3B-Instruct | "Qwen RESEARCH LICENSE AGREEMENT", release date 19 Sep 2024; secondary sources: non-commercial research/evaluation; commercial use needs a separate licence from Alibaba Cloud (search summary of HF mirrors; primary LICENSE file UNVERIFIED) | Qwen2.5-3B-Instruct-GGUF exists (UNVERIFIED this session) | Qwen2.5 claims 29+ languages (UNVERIFIED) | `qwen2.5:3b` about 1.9 GB (search summary) | Commercial restriction conflicts with selling FITRON | reject for production; optional for internal benchmarking only |
| Qwen3-4B | Apache-2.0 (same statement) | Qwen3-4B-GGUF (UNVERIFIED) | as Qwen3 | about 2.5 GB Q4 (UNVERIFIED) | Better reasoning, slower on CPU | optional (upgrade path if CPU budget allows) |
| Hugging Face model licensing docs (hub-docs repositories-licenses.md) | Explains `license:` card field; `license: other` requires a LICENSE file and `license_name` (verified via raw GitHub) | n/a | n/a | n/a | Use the card field, then read the LICENSE file; third-party quantisations may mislabel licences | adopt as process |
| Ollama library entries | qwen3:1.7b 1.4 GB, 40K context (search summary); qwen2.5:3b 1.9 GB (search summary) | n/a | n/a | n/a | Pages not retrievable; sizes UNVERIFIED first-hand | informational |

## Speech

| Resource | Contribution | Maintenance | Compatibility | License | Security | Local | Downloads | Limitations | DECISION |
|---|---|---|---|---|---|---|---|---|---|
| faster-whisper 1.2.1 (SYSTRAN) | STT on CTranslate2; `sellagent_speech/stt.py` | 1.2.1 released 31 Oct 2025 (PyPI); 25.9k stars; Silero VAD v6 bundled (verified) | Python >=3.9; `ctranslate2>=4.0,<5`; ctranslate2 4.8.3 (13 Oct 2026) ships `cp312-win_amd64` wheels (verified) | MIT (verified PyPI and GitHub) | Models auto-download from HF unless a local path is given; pin to `models_dir` | yes | Systran CTranslate2 conversions (OpenAI Whisper weights, MIT): tiny model.bin 75.5 MB, base 145 MB, small 484 MB, medium.en 1.53 GB, large-v3 3.09 GB (HF file listings via search summary); int8 is applied at load (`compute_type="int8"`), README CPU benchmark small/int8 1477 MB RAM | Hindi accuracy drops below `small`; `medium` is slow on CPU | adopt (`small`, int8) |
| Piper (OHF-Voice/piper1-gpl, `piper-tts` 1.8.0) | TTS; `sellagent_speech/tts.py` | v1.8.0 released 4 Sep 2026 (PyPI/GitHub); 5.9k stars; old rhasspy/piper archived 6 Oct 2025 with "Development has moved" notice (verified) | `piper_tts-1.8.0-cp39-abi3-win_amd64.whl` (verified); ONNX Runtime CPU | GPL-3.0-or-later (PyPI) / COPYING = GPLv3 (verified). rhasspy/piper was MIT. No official reason published; it embeds espeak-ng (GPL-3.0) for phonemisation (search summary) | Pure local | yes | Voices from rhasspy/piper-voices (HF, unreachable): Hindi `hi_IN-pratham-medium`, `hi_IN-priyamvada-medium` exist (VOICES.md verified); English `en_US-lessac-{low,medium,high}`; medium `.onnx` typically about 60-65 MB (UNVERIFIED); per-voice licences in each MODEL_CARD, Piper says "some voices may have restrictive licenses" | GPL means our Python process importing `piper` is a combined work; see LICENSES/README.md | adopt with isolation: run the `piper` CLI as a subprocess or pin the MIT `rhasspy/piper` 2023.11.14-2 binary; Hindi voices to be auditioned |
| silero-vad (snakers4) | Neural VAD, 8/16 kHz, about 2 MB model, <1 ms per 30 ms chunk | v6.2.3 (23 Sep 2026); 10.5k stars (verified) | PyPI `silero-vad` 6.2.3 requires `torch>=1.12` (heavy); ONNX extra `onnxruntime>=1.16.1`; can load the `.onnx` directly with onnxruntime without torch | MIT (LICENSE verified; README badge mislabelled) | local | yes | silero_vad.onnx about 2 MB | torch dependency if using the package | optional: use the ONNX file with onnxruntime (already a Piper dependency); keep energy VAD as fallback |
| webrtcvad (wiseman/py-webrtcvad) | GMM VAD, 8/16/32/48 kHz, 10/20/30 ms frames | 2.0.10 (Jan 2017 on PyPI); last commit 15 Feb 2021; sdist only, needs MSVC on Windows (verified) | `webrtcvad-wheels` 2.0.14.post1 provides wheels incl. Python 3.10-3.14 (search/PyPI, cp312 win wheel inferred) | MIT + BSD for WebRTC code (verified) | local | yes | none | Unmaintained upstream | optional (`webrtcvad-wheels`), already supported as optional in `vad.py` |

## Indic TTS alternatives (if Piper Hindi voices are inadequate)

| Resource | License | Notes | DECISION |
|---|---|---|---|
| AI4Bharat/Indic-TTS (github) | MIT (verified); 13 languages incl. Hindi; FastPitch + HiFi-GAN; checkpoints via GitHub release `v1-checkpoints-release`; 412 stars | Needs PyTorch/NeMo-style inference; heavier than Piper; sizes not listed | optional (fallback Hindi voice) |
| ai4bharat/indic-parler-tts (HF) | Reported Apache-2.0 by most aggregators, MIT by AIKosh; gated repo; UNVERIFIED (HF unreachable) | Parler-TTS, transformer decoder; too slow for CPU real time | reject for live use; optional for offline prompt audio |
| facebook/mms-tts-hin | "The MMS code and model weights are released under the CC-BY-NC 4.0 license" (fairseq MMS README, verified); Hindi TTS coverage implied by 1,100+ languages (hin not confirmed on that page) | Non-commercial | reject |

## Application framework and data

| Resource | Contribution | Maintenance | Compatibility | License | Notes | DECISION |
|---|---|---|---|---|---|---|
| PySide6-Essentials 6.8.3 | Desktop UI | 6.8.3 uploaded 27 Mar 2025 with `cp39-abi3-win_amd64` wheel; latest 6.12.0 (8 Oct 2026, requires Python >=3.10,<3.16) (verified PyPI) | Python 3.12 ok | "LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only" or commercial (PyPI metadata; "PySide6 is available under both Open Source (LGPLv3 or GPLv2 or GPLv3) and commercial license") | LGPL section 4 obligations for the packaged exe: notice that Qt is used, ship LGPL/GPL texts, keep Qt as replaceable shared libraries (PyInstaller one-dir, not one-file, or document relinking), no static linking; Essentials excludes Addons | adopt |
| FastAPI 0.143.3 | Local API | current (verified PyPI) | Python >=3.10 | MIT | | adopt |
| SQLAlchemy 2.1.x | ORM | 2.1.5 current; 2.1.4 pinned (verified) | | MIT | | adopt |
| Alembic 1.20.0 | migrations | current (verified) | | MIT | | adopt |
| SQLite FTS5 | Knowledge-base search (`sellagent_kb`) | Docs at sqlite.org/fts5.html not retrievable. Local check: CPython's bundled SQLite 3.45.1 reports `ENABLE_FTS5` and `unicode61` tokenised and matched a Devanagari query (verified in container, Linux build; python.org Windows builds also ship FTS5, UNVERIFIED this session) | | Public domain | Use `unicode61` tokenizer with `remove_diacritics 0` for Hindi; trigram tokenizer for substring search | adopt |
| Android Telecom docs (developer.android.com/develop/connectivity/telecom) | Defines ConnectionService vs InCallService, roles, Core-Telecom | verified | | Google docs licence (CC-BY 4.0 / Apache-2.0 samples) | Confirms no audio-stream access; see docs/TELECOM_FEASIBILITY.md | reference |
| Android Studio | Builds companion and diagnostic APKs | Stable "Rabbit 1" 2026.2.1 (verified releases page) | Windows 11 x64 | Android SDK License Agreement (proprietary, click-through; open-source components under their own licences) | Not redistributed | adopt (build tool) |

## Reference project: github.com/vikrant-project/voice-agent

Exists (verified 2026-10-18). Public repo, description "Offline Voice Assistant + Chatbot with Hindi & English support using Ollama, Whisper, and Piper TTS". Structure: `main.py` (FastAPI, port 8080), `database.py` (SQLite chat history), `ollama_client.py` (llama3), `lang_detect.py`, `voice_in.py` (faster-whisper), `voice_out.py` (Piper), `static/` web UI, `install.sh`, `run.sh`, `setup_ssl.sh`, docs for HTTPS/VPS setup. 3 stars, 0 forks, 6 commits, all dated 4 Apr 2026, authors `vikrant-project` and `emergent-agent-e1` (an AI-agent generated initial commit). README states "MIT License" but no LICENSE file was visible in the listing (UNVERIFIED). No telephony, no Android, no compliance logic, no tests. Security: `setup_ssl.sh`/VPS scripts imply internet exposure. DECISION: reject as a dependency; useful only as a sanity check that the Ollama + faster-whisper + Piper stack handles Hindi/English in one process. Nothing in it should be copied without a confirmed licence file.
