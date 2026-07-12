#!/bin/zsh
set -euo pipefail

ROOT="${0:A:h:h}"
DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
MODULE_CACHE="${ROOT}/build/swift-module-cache"
SWIFT_HOME="${ROOT}/build/swift-home"

if [[ ! -x "${DEVELOPER_DIR}/usr/bin/xcodebuild" ]]; then
  print -u2 "Full Xcode is required at ${DEVELOPER_DIR}."
  exit 1
fi

export DEVELOPER_DIR
export CLANG_MODULE_CACHE_PATH="${MODULE_CACHE}"
export SWIFTPM_MODULECACHE_OVERRIDE="${MODULE_CACHE}"
mkdir -p \
  "${SWIFT_HOME}/Library/org.swift.swiftpm/configuration" \
  "${SWIFT_HOME}/Library/org.swift.swiftpm/security" \
  "${SWIFT_HOME}/Library/Caches/org.swift.swiftpm"
export HOME="${SWIFT_HOME}"

swift test \
  --disable-sandbox \
  --package-path "${ROOT}/app" \
  --scratch-path "${ROOT}/build/swiftpm"
