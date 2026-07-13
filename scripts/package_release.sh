#!/bin/zsh
set -euo pipefail

ROOT="${0:A:h:h}"
DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
DERIVED_DATA="${ROOT}/build/DerivedData"
DIST="${ROOT}/dist"
EXPECTED_UV_VERSION="0.11.28"

if [[ ! -x "${DEVELOPER_DIR}/usr/bin/xcodebuild" ]]; then
  print -u2 "Full Xcode is required at ${DEVELOPER_DIR}."
  exit 1
fi

if [[ -n "${BILLIE_FLOW_UV:-}" ]]; then
  UV="${BILLIE_FLOW_UV:A}"
elif command -v uv >/dev/null 2>&1; then
  UV="$(command -v uv)"
  UV="${UV:A}"
else
  print -u2 "Packaging needs the pinned uv ${EXPECTED_UV_VERSION} executable."
  exit 1
fi

UV_VERSION="$("${UV}" --version)"
if [[ "${UV_VERSION}" != "uv ${EXPECTED_UV_VERSION}"* ]]; then
  print -u2 "Expected uv ${EXPECTED_UV_VERSION}; found ${UV_VERSION}."
  exit 1
fi

if [[ "$(lipo -archs "${UV}")" != "arm64" ]]; then
  print -u2 "The bundled uv executable must be Apple Silicon arm64."
  exit 1
fi

UV_PREFIX="${UV:h:h}"
for license in LICENSE-APACHE LICENSE-MIT; do
  if [[ ! -f "${UV_PREFIX}/${license}" ]]; then
    print -u2 "The uv distribution license ${license} is missing beside ${UV}."
    exit 1
  fi
done

export DEVELOPER_DIR
rm -rf "${DERIVED_DATA}" "${DIST}/Billie Flow.app"
mkdir -p "${DIST}"

xcodebuild \
  -project "${ROOT}/app/BillieFlow.xcodeproj" \
  -scheme BillieFlow \
  -configuration Release \
  -derivedDataPath "${DERIVED_DATA}" \
  ARCHS=arm64 \
  CODE_SIGNING_ALLOWED=NO \
  build

SOURCE_APP="${DERIVED_DATA}/Build/Products/Release/Billie Flow.app"
if [[ ! -d "${SOURCE_APP}" ]]; then
  print -u2 "Release build completed without the expected app at ${SOURCE_APP}."
  exit 1
fi
ditto "${SOURCE_APP}" "${DIST}/Billie Flow.app"

FINAL_APP="${DIST}/Billie Flow.app"
BOOTSTRAP="${FINAL_APP}/Contents/Resources/Bootstrap"
mkdir -p "${BOOTSTRAP}/worker"
ditto "${ROOT}/worker/src" "${BOOTSTRAP}/worker/src"
ditto "${ROOT}/worker/pyproject.toml" "${BOOTSTRAP}/worker/pyproject.toml"
ditto "${ROOT}/worker/requirements.lock" "${BOOTSTRAP}/worker/requirements.lock"
ditto "${UV}" "${BOOTSTRAP}/uv"
ditto "${UV_PREFIX}/LICENSE-APACHE" "${BOOTSTRAP}/uv-LICENSE-APACHE"
ditto "${UV_PREFIX}/LICENSE-MIT" "${BOOTSTRAP}/uv-LICENSE-MIT"
chmod 755 "${BOOTSTRAP}/uv"
xattr -c "${BOOTSTRAP}/uv"

plutil -lint "${FINAL_APP}/Contents/Info.plist"

if [[ "$(lipo -archs "${FINAL_APP}/Contents/MacOS/Billie Flow")" != "arm64" ]]; then
  print -u2 "The Release app must be Apple Silicon arm64 only."
  exit 1
fi

codesign --force --sign - --timestamp=none "${BOOTSTRAP}/uv"
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

VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "${FINAL_APP}/Contents/Info.plist")"
ARCHIVE_NAME="Billie-Flow-v${VERSION}-apple-silicon.zip"
CHECKSUM_NAME="${ARCHIVE_NAME}.sha256"
rm -f "${DIST}/${ARCHIVE_NAME}" "${DIST}/${CHECKSUM_NAME}"
ditto -c -k --sequesterRsrc --keepParent "${FINAL_APP}" "${DIST}/${ARCHIVE_NAME}"
(
  cd "${DIST}"
  shasum -a 256 "${ARCHIVE_NAME}" > "${CHECKSUM_NAME}"
)

print "Release app: ${FINAL_APP}"
print "Release archive: ${DIST}/${ARCHIVE_NAME}"
print "Release checksum: ${DIST}/${CHECKSUM_NAME}"
