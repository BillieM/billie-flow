#!/bin/zsh
set -euo pipefail

ROOT="${0:A:h:h}"
DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
DERIVED_DATA="${ROOT}/build/DerivedData"
DIST="${ROOT}/dist"

if [[ ! -x "${DEVELOPER_DIR}/usr/bin/xcodebuild" ]]; then
  print -u2 "Full Xcode is required at ${DEVELOPER_DIR}."
  exit 1
fi

export DEVELOPER_DIR
rm -rf "${DERIVED_DATA}" "${DIST}/Billie Flow.app"
mkdir -p "${DIST}"

xcodebuild \
  -project "${ROOT}/app/BillieFlow.xcodeproj" \
  -scheme BillieFlow \
  -configuration Release \
  -derivedDataPath "${DERIVED_DATA}" \
  CODE_SIGNING_ALLOWED=NO \
  build

SOURCE_APP="${DERIVED_DATA}/Build/Products/Release/Billie Flow.app"
if [[ ! -d "${SOURCE_APP}" ]]; then
  print -u2 "Release build completed without the expected app at ${SOURCE_APP}."
  exit 1
fi
ditto "${SOURCE_APP}" "${DIST}/Billie Flow.app"

plutil -lint "${DIST}/Billie Flow.app/Contents/Info.plist"

FINAL_APP="${DIST}/Billie Flow.app"
for nested_root in Frameworks PlugIns XPCServices Helpers; do
  nested_path="${FINAL_APP}/Contents/${nested_root}"
  [[ -d "${nested_path}" ]] || continue
  while IFS= read -r nested_code; do
    codesign --force --sign - --timestamp=none "${nested_code}"
  done < <(
    find -d "${nested_path}" \
      \( -type d \( -name '*.framework' -o -name '*.appex' -o -name '*.xpc' -o -name '*.app' \) \
      -o -type f \( -name '*.dylib' -o -perm -111 \) \) -print
  )
done

codesign --force --sign - --timestamp=none "${FINAL_APP}"
codesign --verify --deep --strict "${FINAL_APP}"
print "Release app: ${DIST}/Billie Flow.app"
