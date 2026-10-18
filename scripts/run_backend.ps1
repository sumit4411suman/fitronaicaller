$env:PYTHONPATH = "services\local-backend;services\ai-engine;services\speech-engine;services\knowledge-base;packages\shared-protocol"
.\.venv\Scripts\python.exe -m sellagent_backend.main @args
