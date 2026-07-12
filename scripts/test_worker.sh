#!/bin/zsh
set -euo pipefail

ROOT="${0:A:h:h}"
TEST_VENV="${ROOT}/build/worker-test-venv"
UV_CACHE_DIR="${ROOT}/build/uv-cache"
export UV_CACHE_DIR

if command -v uv >/dev/null 2>&1; then
  UV="$(command -v uv)"
elif [[ -x "${HOME}/.local/bin/uv" ]]; then
  UV="${HOME}/.local/bin/uv"
else
  print -u2 "Worker tests need uv; run scripts/bootstrap_worker.sh first."
  exit 1
fi

"${UV}" venv --clear --python 3.12 "${TEST_VENV}"
"${UV}" pip install --python "${TEST_VENV}/bin/python" -r "${ROOT}/worker/requirements-dev.lock"

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="${ROOT}/worker/src" \
  "${TEST_VENV}/bin/python" -m pytest -p no:cacheprovider "${ROOT}/worker/tests" -q
