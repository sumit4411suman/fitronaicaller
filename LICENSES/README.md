# SELL AGENT - Third-party License Inventory

Inventory date: 2026-10-18. SELL AGENT itself is proprietary (see pyproject.toml). Licence names were read from PyPI JSON metadata (`license` / `license_expression`) or the project's GitHub page in this session unless marked otherwise. Before each release, regenerate the exact list with `pip-licenses --with-urls --format=markdown` inside the build environment and copy the licence texts into this folder.

## Python runtime dependencies (requirements*.txt)

| Package (pinned) | License | Link | Attribution / obligations when shipping the Windows build |
|---|---|---|---|
| fastapi 0.143.3 | MIT | https://pypi.org/project/fastapi/ | Include copyright notice and MIT text |
| uvicorn 0.54.0 | BSD-3-Clause | https://pypi.org/project/uvicorn/ | Include notice; no endorsement use of names |
| pydantic 2.14.1 | MIT (PyPI license field not visible in truncated JSON; MIT per project LICENSE, UNVERIFIED this session) | https://pypi.org/project/pydantic/ | Include notice |
| pydantic-settings 2.16.0 | MIT | https://pypi.org/project/pydantic-settings/ | Include notice |
| sqlalchemy 2.1.4 | MIT | https://pypi.org/project/SQLAlchemy/ | Include notice |
| alembic 1.20.0 | MIT | https://pypi.org/project/alembic/ | Include notice |
| httpx 0.28.1 | BSD-3-Clause | https://pypi.org/project/httpx/ | Include notice |
| websockets 17.2 | BSD-3-Clause | https://pypi.org/project/websockets/ | Include notice |
| phonenumbers 9.0.41 | Apache-2.0 | https://pypi.org/project/phonenumbers/ | Include LICENSE and NOTICE if present; state modifications (none) |
| openpyxl 3.1.5 | MIT | https://pypi.org/project/openpyxl/ | Include notice |
| cryptography 50.0.2 | Apache-2.0 OR BSD-3-Clause (dual) | https://pypi.org/project/cryptography/ | Choose one and include its text; bundles OpenSSL (Apache-2.0) in wheels |
| python-multipart 0.0.32 | Apache-2.0 | https://pypi.org/project/python-multipart/ | Include notice |
| numpy 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | https://pypi.org/project/numpy/ | Include LICENSE.txt and LICENSES_bundled.txt (OpenBLAS etc.) |
| PySide6-Essentials 6.8.3 | LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only (or Qt commercial) | https://pypi.org/project/PySide6-Essentials/ | COPYLEFT (weak). Under LGPL-3.0 section 4: give prominent notice that Qt/PySide6 is used; ship the LGPL-3.0 and GPL-3.0 texts; keep Qt DLLs and PySide6 modules as replaceable shared libraries (PyInstaller `--onedir`; do not statically link; do not obfuscate the Qt directory); provide our unmodified-Qt statement; installation information where section 6 of GPL applies. Essentials only; Addons are not used. |
| faster-whisper 1.2.1 | MIT | https://pypi.org/project/faster-whisper/ | Include notice; depends on ctranslate2 (MIT), tokenizers (Apache-2.0), onnxruntime (MIT), av (BSD-3 / bundles FFmpeg LGPL-2.1+ - check av wheel notices) |
| piper-tts 1.8.0 | GPL-3.0-or-later | https://pypi.org/project/piper-tts/ , https://github.com/OHF-Voice/piper1-gpl | COPYLEFT (strong). See section below. |
| sounddevice 0.5.6 | MIT (bundles PortAudio, MIT-style PortAudio licence) | https://pypi.org/project/sounddevice/ | Include both notices |
| keyring 25.7.0 | MIT | https://pypi.org/project/keyring/ | Include notice |
| psutil 7.2.2 | BSD-3-Clause | https://pypi.org/project/psutil/ | Include notice |
| pytest 9.1.1 (dev only) | MIT | https://pypi.org/project/pytest/ | Not shipped |
| pyinstaller 6.22.3 (dev only) | "GPLv2-or-later with a special exception which allows to use PyInstaller to build and distribute non-free programs (including commercial ones)" | https://pypi.org/project/pyinstaller/ | Bootloader exception lets the frozen app stay proprietary; PyInstaller itself is not shipped |
| ruff, mypy (dev only) | MIT | pypi | Not shipped |
| webrtcvad-wheels (optional) | MIT + BSD (WebRTC VAD code) | https://pypi.org/project/webrtcvad-wheels/ | Include both notices |
| llama.cpp / llama-server (optional external LLM runtime, not bundled) | MIT | https://github.com/ggml-org/llama.cpp | Used over its local HTTP API (`ai.llm_provider = llamacpp`); include notice if a binary is ever redistributed |
| Silero VAD v6 ONNX model (bundled inside faster-whisper as `faster_whisper/assets/silero_vad_v6.onnx`) | MIT | https://github.com/snakers4/silero-vad | Used by `sellagent_speech.vad.SileroVAD`; covered by the faster-whisper/Silero MIT notices |
| onnxruntime (transitive, via piper/silero) | MIT | https://pypi.org/project/onnxruntime/ | Include notice (UNVERIFIED version) |

## Android companion libraries

| Library | License | Link | Obligations |
|---|---|---|---|
| AndroidX (core, appcompat, lifecycle, work, core-telecom) | Apache-2.0 (verified github.com/androidx/androidx) | https://github.com/androidx/androidx | Include Apache notice in the app's licences screen (e.g. Gradle `oss-licenses-plugin`) |
| OkHttp 5.x | Apache-2.0 (verified) | https://github.com/square/okhttp | Same |
| kotlinx.coroutines (and Kotlin stdlib) | Apache-2.0 (verified) | https://github.com/Kotlin/kotlinx.coroutines | Same |
| Android SDK / Android Studio | Android Software Development Kit License Agreement (proprietary click-through) | https://developer.android.com/studio/terms | Build-time only; not redistributed |

## Models and voices

| Asset | License | Source | Notes |
|---|---|---|---|
| Qwen3-1.7B, Qwen3-4B (GGUF) | Apache-2.0 ("All our open-weight models are licensed under Apache 2.0", github.com/QwenLM/Qwen3, verified) | https://huggingface.co/Qwen | Include Apache notice; state model name and that it is unmodified or quantised |
| Qwen2.5-3B-Instruct | Qwen RESEARCH LICENSE AGREEMENT (19 Sep 2024); non-commercial per secondary sources; primary LICENSE not retrievable | https://huggingface.co/Qwen/Qwen2.5-3B-Instruct | COMMERCIAL RESTRICTION. Not for production use in SELL AGENT. |
| Whisper weights (tiny/base/small/medium/large-v3) | MIT (OpenAI) | https://github.com/openai/whisper | Systran CTranslate2 conversions (Systran/faster-whisper-*) keep MIT; include OpenAI notice |
| Silero VAD model | MIT | https://github.com/snakers4/silero-vad | Include notice |
| Piper voices (en_US-lessac-medium, hi_IN-pratham-medium, hi_IN-priyamvada-medium) | Per-voice; each voice's MODEL_CARD in rhasspy/piper-voices states the dataset licence; Piper warns "some voices may have restrictive licenses" | https://huggingface.co/rhasspy/piper-voices | UNVERIFIED in this session (HF unreachable). Record the MODEL_CARD text in this folder before shipping any voice; do not ship voices whose dataset licence is non-commercial. |
| AI4Bharat Indic-TTS (fallback) | MIT (repo); checkpoint licence UNVERIFIED | https://github.com/AI4Bharat/Indic-TTS | Not shipped by default |
| facebook/mms-tts-hin | CC-BY-NC 4.0 (fairseq MMS README, verified) | https://github.com/facebookresearch/fairseq/tree/main/examples/mms | COMMERCIAL RESTRICTION. Rejected. |

## Copyleft and restriction flags

1. piper-tts 1.8.0 is GPL-3.0-or-later (the 2023 rhasspy/piper code was MIT; the new OHF-Voice/piper1-gpl embeds espeak-ng, itself GPL-3.0, and the repository's COPYING is GPLv3). GPL-3.0 section 5(c) requires that a work "based on" the Program be licensed "as a whole" under the GPL when conveyed, and section 1 "Corresponding Source" covers all source needed to generate the object code. Importing `piper` into the SELL AGENT Python process and distributing the frozen application together is the situation the FSF treats as a single combined program. Options, in order of preference:
   - Invoke a separately installed `piper` executable (or `python -m piper`) as a child process over stdin/stdout, distributed as a separate optional download or installed by the operator. GPL-3.0 section 5's "aggregate" paragraph: "Inclusion of a covered work in an aggregate does not cause this License to apply to the other parts of the aggregate." Document the interface in `sellagent_speech/tts.py` and do not bundle piper inside the PyInstaller archive.
   - Pin the last MIT release of rhasspy/piper (2023.11.14-2 binaries, archived repository) for the bundled build; voices are compatible; no new fixes.
   - Release the whole speech-engine process under GPL-3.0 as a separate program; not compatible with the proprietary desktop as one distribution.
   Decision for v0.1: subprocess invocation of an operator-installed piper; `requirements-speech.txt` stays optional and is not frozen into the proprietary executable.
2. PySide6 LGPL-3.0: acceptable for a proprietary app only with dynamic linking and the section 4 notices; `--onefile` builds that unpack Qt at runtime are still dynamic, but keep `--onedir` to make relinking obviously possible.
3. PyInstaller GPL-2.0+ with bootloader exception: no obligation on the frozen app.
4. Qwen2.5-3B-Instruct (Qwen Research License) and MMS-TTS (CC-BY-NC 4.0): commercial restrictions; excluded from production.
5. cryptography and numpy ship bundled third-party code (OpenSSL, OpenBLAS); include their bundled licence files from the wheels.
6. Piper voices: per-voice dataset licences; verify each MODEL_CARD before distribution.

## Files to add before first release

- `LICENSES/LGPL-3.0.txt`, `LICENSES/GPL-3.0.txt`, `LICENSES/GPL-2.0.txt` (Qt choice of licence), `LICENSES/Apache-2.0.txt`, `LICENSES/MIT-notices.txt` (aggregated), `LICENSES/BSD-notices.txt`, `LICENSES/numpy-bundled.txt`, `LICENSES/piper-voices/<voice>/MODEL_CARD.md`.
- A "Third-party notices" dialog in the desktop app that renders this folder.

## Evaluated telephony-bridge projects (no code copied)

These were studied for the calling architecture (`docs/TELEPHONY_BRIDGE_EVALUATION.md`). **None of their source is
incorporated into SELL AGENT.** Where an idea was adopted it is a public protocol or design pattern, re-implemented.

| Project | Licence | How it relates to us |
|---|---|---|
| sidinsearch/AgentCall | AGPL-3.0-only (NOTICE flags unresolved upstream provenance) | Reference only. AGPL + the privileged/root model make its code unusable here; **not copied**. |
| OriginStackHQ/GSM2SIP | **No LICENSE file** (all rights reserved) | GSM↔SIP gateway *idea* reused, re-implemented from Asterisk's public interfaces; **code not copied** (no licence grants permission). |
| koreapyj/asterisk-chan-modemmanager | GPL-2.0-only | Runs as a **separate Asterisk process**; SELL AGENT connects over a loopback AudioSocket socket, so GPL does not reach our backend. **Not linked, not copied.** If an Asterisk bundle is ever redistributed it keeps its own licence + corresponding source. |
| ictinnovations/asterisk-ai-voice-agent | MIT | We reuse the **AudioSocket wire protocol** (a public Asterisk format) and its outbound-pacing lesson, re-implemented in `telecom/audiosocket.py`. We did **not** adopt its sidecar or its paid cloud providers. MIT attribution noted here. |

AudioSocket is a documented Asterisk protocol (`app_audiosocket`); a clean-room re-implementation of a wire
format carries no licence obligation.
