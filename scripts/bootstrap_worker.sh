#!/bin/zsh
set -euo pipefail

ROOT="${0:A:h:h}"
APP_SUPPORT="${HOME}/Library/Application Support/Billie Flow"
RUNTIME_ROOT="${APP_SUPPORT}/runtime"
VENV="${RUNTIME_ROOT}/.venv"
WORKER_COPY="${RUNTIME_ROOT}/worker"

if [[ ! -f "${ROOT}/worker/requirements.lock" ]]; then
  print -u2 "worker/requirements.lock is missing; run from a complete Billie Flow checkout."
  exit 1
fi

if command -v uv >/dev/null 2>&1; then
  UV="$(command -v uv)"
elif [[ -x "${HOME}/.local/bin/uv" ]]; then
  UV="${HOME}/.local/bin/uv"
elif command -v brew >/dev/null 2>&1; then
  print "Installing the uv Python runtime manager with Homebrew…"
  brew install uv
  UV="$(command -v uv)"
else
  print -u2 "Billie Flow needs uv. Install it from https://docs.astral.sh/uv/ then rerun this command."
  exit 1
fi

mkdir -p "${RUNTIME_ROOT}"
rm -rf "${WORKER_COPY}.next"
ditto "${ROOT}/worker" "${WORKER_COPY}.next"
rm -rf "${WORKER_COPY}"
mv "${WORKER_COPY}.next" "${WORKER_COPY}"

"${UV}" venv --clear --python 3.12 --seed "${VENV}"
"${UV}" pip install --python "${VENV}/bin/python" -r "${WORKER_COPY}/requirements.lock"
"${UV}" pip install --python "${VENV}/bin/python" --no-deps --no-build-isolation "${WORKER_COPY}"

print "Prefetching the fixed Billie Flow models into the existing Hugging Face cache…"
"${VENV}/bin/python" -m billie_flow_worker.prefetch

"${VENV}/bin/python" - <<'PY'
import sys
if sys.version_info[:2] != (3, 12):
    raise SystemExit(f"expected Python 3.12, found {sys.version.split()[0]}")
import billie_flow_worker
print(f"Billie Flow worker ready with Python {sys.version.split()[0]}.")
PY

print "Runtime: ${RUNTIME_ROOT}"
print "Hugging Face cache: ${HF_HOME:-${HOME}/.cache/huggingface}"
