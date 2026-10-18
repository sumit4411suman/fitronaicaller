# Dependencies (pinned, verified installable on Python 3.12 x86-64 in this session)

| Package | Version | Role | Verified here |
| --- | --- | --- | --- |
| fastapi | 0.143.3 | REST + WebSocket backend | yes (tests) |
| uvicorn[standard] | 0.54.0 | ASGI server, TLS for LAN listener | yes (e2e) |
| pydantic / pydantic-settings | 2.14.1 / 2.16.0 | validation, settings | yes |
| SQLAlchemy | 2.1.4 | ORM | yes |
| alembic | 1.20.0 | migrations | yes |
| httpx | 0.28.1 | local AI clients, tests | yes |
| websockets | 17.2 | e2e client, desktop WS client | yes |
| phonenumbers | 9.0.41 | E.164 validation | yes |
| openpyxl | 3.1.5 | XLSX import/export | yes |
| cryptography | 50.0.2 | backup encryption, TLS cert | yes |
| python-multipart | >=0.0.20 | uploads | yes |
| numpy | 2.5.4 | VAD, audio | yes |
| PySide6-Essentials | 6.8.3 | desktop UI (QtMultimedia included) | installed; UI tests offscreen |
| faster-whisper / ctranslate2 | 1.2.1 / 4.8.3 | STT | import verified; no model run |
| piper-tts / onnxruntime | 1.8.0 / 1.31.0 | TTS | import verified; no voice run; GPL-3.0 |
| sounddevice | 0.5.6 | optional PC audio | import needs PortAudio (bundled on Windows wheels) |
| psutil | 7.2.2 | RAM/benchmark metrics | yes |
| pytest / pytest-asyncio | 9.1.1 / 1.4.0 | tests | yes |
| pyinstaller | 6.22.3 | Windows packaging | not run (Linux session) |

Python 3.13 is not supported by the pins (PySide6 6.8.3 wheels target <=3.12 in our matrix); use 3.12.x.
Licences: `LICENSES/README.md`.
