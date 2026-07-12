#!/bin/zsh
set -euo pipefail

ROOT="${0:A:h:h}"
cd "${ROOT}"

python3 scripts/validate_worker_contract.py
scripts/test_worker.sh
scripts/test_swift.sh
scripts/test_xcode.sh

if [[ -f experiments/voice-memo/results.json ]]; then
  python3 scripts/validate_results.py experiments/voice-memo/results.json
fi

if [[ "${1:-}" == "--full" ]]; then
  scripts/package_release.sh
fi
