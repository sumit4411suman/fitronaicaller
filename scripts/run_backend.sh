#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="services/local-backend:services/ai-engine:services/speech-engine:services/knowledge-base:packages/shared-protocol"
exec "${PYTHON:-.venv/bin/python}" -m sellagent_backend.main "$@"
