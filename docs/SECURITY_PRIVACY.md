# Security and privacy

## Principles
Local by default, least privilege, explicit opt-in for anything that leaves the machine, no silent uploads, no telemetry,
no disabled OS protections.

## Controls implemented

| Area | Control | Where |
| --- | --- | --- |
| Network | API bound to 127.0.0.1; refuses non-loopback bind | `main.py` |
| Network | LAN listener opt-in (`network.lan_pairing_enabled`), separate port 8766, TLS, device routes only, 403 for anything else | `lan.py`, `app.create_device_app` |
| TLS | self-signed P-256 cert generated locally; phone pins SHA-256 fingerprint shown on the pairing screen; validation never disabled | `security/tls.py`, Android trust manager |
| Pairing | 8-char code from an unambiguous alphabet, 5-minute TTL, 5 attempts, per-IP rate limit, mutual approval (phone submits, Windows approves), token shown once | `security/pairing.py`, `api/v1/devices.py` |
| Tokens | 256-bit random, stored as SHA-256 only, 90-day expiry, revocation closes live sockets | `security/tokens.py`, `devices.revoke` |
| Local token | DPAPI (CryptProtectData, user scope) on Windows; 0600 file elsewhere; rotation endpoint | `security/secret_store.py` |
| Input | strict Pydantic models (`extra=forbid`), phone validation via libphonenumber, import size/row limits, file type whitelist, control-char stripping, formula-injection neutralisation on export | `api/schemas.py`, `services/import_export.py` |
| SQL | SQLAlchemy parameters everywhere; FTS query built from tokenised terms | `sellagent_kb/service.py` |
| Paths | backup verify/restore accept only files inside the backups directory | `api/v1/settings.py` |
| Secrets in logs | audit `redact()` removes token/password/api_key fields; tokens never logged | `services/audit.py` |
| Audit | append-only `audit_events` for consent, opt-out, suppression, campaign authorisation, dispatch, emergency stop, pairing, settings, backup, knowledge approval | everywhere via `audit.record` |
| Backup | SQLite online backup; AES-256-GCM with scrypt-derived key, header authenticated; integrity check before restore; pre-restore safety copy; retention | `services/backup.py` |
| Retention | transcript retention job (`privacy.transcript_retention_days`), log rotation, backup count | settings + `retention/run` |
| Recording | off by default; `privacy.record_calls` exists but no recording pipeline ships; disclosure text configurable | settings |
| Prompt injection | imported knowledge is untrusted; regex + hidden-unicode screening; approval requires acknowledgement; system prompt instructs the model to treat facts and prospect words as data | `sellagent_kb`, `engine.SYSTEM_PROMPT` |
| LLM authority | consent, suppression, emergency stop, authorization and the release gate are enforced in code paths the model cannot reach | `eligibility.py`, `states.py` |
| Android | documented APIs only, Keystore-backed storage, foreground services only when needed, no hidden APIs/root/accessibility abuse | `docs/ANDROID_APPS.md` |

## Not done / limitations
* Windows DPAPI code path is implemented but was not executed in this Linux build session (covered by the Windows CI job when it runs).
* The desktop talks to the backend over plain HTTP on loopback (standard for local apps); the LAN side is TLS.
* No code signing certificate: unsigned installers show SmartScreen warnings. Legitimate options: OV/EV code-signing certificate from a CA, or Azure Trusted Signing. No free option removes SmartScreen reputation warnings.
* Secure deletion of SQLite data is best-effort (`VACUUM` after deletes is not automatic); encrypted backups and full-disk encryption (BitLocker) are the recommended mitigations.

## Threat notes
* A device on the same Wi-Fi can reach the LAN listener only while pairing is enabled, must know the one-time code within 5 minutes and 5 attempts, and still needs the operator to approve on Windows.
* A revoked or expired device token is rejected on both HTTP and WebSocket.
* Emergency stop is reachable from the desktop (HTTP and WebSocket), the Android app, and cancels all open jobs; new jobs are blocked while active.
