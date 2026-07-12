#!/bin/zsh
set -euo pipefail

ROOT="${0:A:h:h}"
DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"

if [[ ! -x "${DEVELOPER_DIR}/usr/bin/xcodebuild" ]]; then
  print -u2 "Full Xcode is required at ${DEVELOPER_DIR}."
  exit 1
fi

export DEVELOPER_DIR
xcodebuild \
  -quiet \
  -project "${ROOT}/app/BillieFlow.xcodeproj" \
  -scheme BillieFlow \
  -configuration Debug \
  -destination 'platform=macOS' \
  -derivedDataPath "${ROOT}/build/XcodeTests" \
  CODE_SIGNING_ALLOWED=NO \
  test
