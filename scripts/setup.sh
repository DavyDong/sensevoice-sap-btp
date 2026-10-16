#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export UV_CACHE_DIR="$PWD/.cache/uv" UV_PYTHON_INSTALL_DIR="$PWD/.cache/python"
if [[ ! -x .venv/bin/python ]]; then uv venv --python 3.11.15 .venv; fi
if [[ "$(uname)" == Darwin ]]; then
  uv pip install --python .venv/bin/python 'torch==2.11.0' 'torchaudio==2.11.0' -r requirements.in
else
  uv pip install --python .venv/bin/python --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match -r requirements-linux.lock
fi
uv pip install --python .venv/bin/python pytest==9.1.1
uv pip check --python .venv/bin/python
.venv/bin/python scripts/download_models.py
echo 'Ready. Run: bash scripts/start.sh'
