# Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Desktop shows "backend not reachable" | backend failed to start or port 8765 busy | run `.\scripts\run_backend.ps1`, read `<data dir>\logs\backend.log`; set `SELLAGENT_PORT` to another port |
| 401 from the API / "local API token invalid" | token file rotated or data dir changed | restart the desktop app (it re-reads `<data dir>\local_api_token`); `SELLAGENT_DATA_DIR` must match |
| Token file cannot be read on another machine | DPAPI is per Windows user | delete `local_api_token`; a new token is generated on next start |
| Call job is `blocked` | eligibility failed | open the job: `eligibility_result.reasons` lists exactly why (consent, suppression, quiet hours, limits, gate) |
| "quiet hours" even in the afternoon | timezone setting | `general.timezone` (default Asia/Kolkata) and quiet hours 21:00-10:00 |
| Autonomous toggle disabled | release gate closed | run the real-device audio tests and confirm inbound and outbound PASS rows; see `docs/TELECOM_FEASIBILITY.md` |
| Phone cannot pair | LAN listener off, firewall, wrong fingerprint | enable `network.lan_pairing_enabled`, allow `python.exe` on private networks for TCP 8766, compare the fingerprint |
| Phone shows certificate error | fingerprint mismatch (certificate regenerated) | forget pairing on the phone, re-pair with the new fingerprint shown on the PC |
| `pairing window closed` | 5-minute TTL or 5 wrong attempts | open a new window |
| AI status "Ollama not reachable" | Ollama not running | start Ollama; check `ai.llm_provider` and `SELLAGENT_OLLAMA_BASE_URL` |
| "model is not installed in Ollama" | pull not done | `ollama pull qwen3:1.7b` or the model manager with network enabled |
| STT "could not load whisper model" | model not downloaded and network disabled | `scripts/download_models.py --whisper small --yes` |
| TTS "no Piper voice configured" | voice missing | download a voice and set `ai.piper_voice_en` / `ai.piper_voice_hi` |
| PortAudio error on Linux dev boxes | `sounddevice` needs libportaudio2 | `apt install libportaudio2`; Windows wheels bundle it |
| Backup "passphrase required" | `backup.encrypt` is on | enter a passphrase (>= 8 chars) or switch encryption off |
| Restore "wrong passphrase or corrupted backup" | AES-GCM tag failed | the passphrase is wrong or the file is damaged |
| Import says duplicates | same E.164 number or same business name already exists | choose `update` or `import_anyway` policy |
| Hindi text shows boxes | missing Devanagari font | Windows: Nirmala UI is built in; Linux: install Noto Sans Devanagari |
| SmartScreen warns on the installer | unsigned binary | expected; see `docs/SECURITY_PRIVACY.md` on code signing |

Logs: `<data dir>\logs\backend.log` (rotating), the Logs & Health screen, and `GET /api/v1/audit` for the audit trail.
