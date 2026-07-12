#!/bin/zsh
set -euo pipefail

ROOT="${0:A:h:h}"
exec python3 "${ROOT}/qa/system_acceptance.py" "$@"
