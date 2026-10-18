# Offline operation

After setup and model downloads, SELL AGENT must work with the network disconnected.

| Function | Needs network? | Notes |
| --- | --- | --- |
| Desktop app, backend, SQLite CRM, import/export, campaigns, call jobs, follow-ups, reports, audit, backup/restore | No | loopback only |
| Knowledge base and FTS5 retrieval | No | SQLite built-in |
| Conversation engine with scripts and guardrails | No | works even with no LLM installed |
| Local LLM (Ollama / llama-server) | No after `ollama pull` | Ollama itself must be running locally |
| faster-whisper STT | No after model download | `local_files_only` unless external network is enabled |
| Piper TTS | No after voice download | |
| Android pairing and device events | Same Wi-Fi LAN only, no internet | the phone's calls still use the Jio network |
| Model downloads (`scripts/download_models.py`, `/ai/models/pull`) | **Yes** | blocked unless `privacy.allow_external_network` is true |
| Optional external providers | none shipped | disabled by design |

Proof procedure (run on the target PC): `python scripts/offline_check.py` with Wi-Fi and Ethernet turned off. It prints
whether the machine is actually offline, then exercises CRM, retrieval, LLM and speech loopback, and writes
`docs/benchmarks/offline_check_last.json`. Status in this release: **procedure provided, not executed** (the build
environment had no models and no target hardware).
