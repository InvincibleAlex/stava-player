#!/usr/bin/env bash
set -euo pipefail

# Builds Stava Player.app, repairs the nested VST bundles and signs the result.
#
# The build deliberately happens OUTSIDE the project directory. This repo lives
# under ~/Documents, which is managed by the iCloud Drive file provider, and that
# provider keeps stamping com.apple.FinderInfo onto directories. codesign refuses
# any bundle carrying it ("resource fork, Finder information, or similar detritus
# not allowed") and stripping the attribute does not help, because it is put back
# straight away. Building in ~/Library/Caches avoids that entirely; only the
# finished artefacts are copied back into dist/.
#
# Set MACOS_SIGN_IDENTITY to sign with a Developer ID instead of ad-hoc ("-").

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
SPEC_FILE="${SPEC_FILE:-$ROOT_DIR/Stava Player mac.spec}"
BUILD_ROOT="${BUILD_ROOT:-$HOME/Library/Caches/stava-player-build}"
IDENTITY="${MACOS_SIGN_IDENTITY:--}"
APP_NAME="Stava Player"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python executable not found: $PYTHON_BIN" >&2
  exit 1
fi

cd "$ROOT_DIR"

echo "[build_mac] Using Python: $PYTHON_BIN"
echo "[build_mac] Using spec:   $SPEC_FILE"
echo "[build_mac] Build root:   $BUILD_ROOT"

rm -rf "$BUILD_ROOT"
mkdir -p "$BUILD_ROOT"

"$PYTHON_BIN" -m PyInstaller --noconfirm \
  --distpath "$BUILD_ROOT/dist" \
  --workpath "$BUILD_ROOT/build" \
  "$SPEC_FILE"

APP_BUNDLE="$BUILD_ROOT/dist/$APP_NAME.app"

# Must run before the app is signed: it rewrites the plugin bundles, which would
# otherwise invalidate an outer signature.
APP_BUNDLE="$APP_BUNDLE" MACOS_SIGN_IDENTITY="$IDENTITY" "$ROOT_DIR/tools/mac/fix_vst_bundles.sh"

# PyInstaller already signed the bundle during BUNDLE; that signature now refers
# to files fix_vst_bundles.sh removed, so drop it and sign the final layout.
rm -rf "$APP_BUNDLE/Contents/_CodeSignature"
codesign --force --timestamp --sign "$IDENTITY" "$APP_BUNDLE"
codesign --verify --deep --strict "$APP_BUNDLE"
echo "[build_mac] Signature verified."

mkdir -p "$ROOT_DIR/dist"
rm -rf "$ROOT_DIR/dist/$APP_NAME.app"
cp -R "$APP_BUNDLE" "$ROOT_DIR/dist/"

echo "[build_mac] Build complete: $ROOT_DIR/dist/$APP_NAME.app"
