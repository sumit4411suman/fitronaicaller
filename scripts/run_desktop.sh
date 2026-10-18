#!/usr/bin/env bash
# Launch SELL AGENT desktop from a source checkout (Linux/macOS dev box; use QT_QPA_PLATFORM=offscreen for headless smoke tests).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="${PYTHON:-python3}"
[ -x ".venv/bin/python" ] && PY=".venv/bin/python"
export PYTHONPATH="services/local-backend:services/ai-engine:services/speech-engine:services/knowledge-base:packages/shared-protocol:apps/windows-desktop${PYTHONPATH:+:$PYTHONPATH}"
exec "$PY" -m sellagent_desktop.main "$@"
