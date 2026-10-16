#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export AUTH_MODE=none HOST=127.0.0.1 PORT="${PORT:-8000}"
exec .venv/bin/python run.py
