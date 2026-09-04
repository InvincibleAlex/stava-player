#!/usr/bin/env bash
set -euo pipefail

# Packages dist/Stava Player.app into a DMG.
#
# Like build_mac.sh, the staging happens outside the project directory: the repo
# sits in an iCloud-managed folder, and staging a signed .app there lets the file
# provider stamp attributes onto the copy that goes into the image. Only the
# finished .dmg is copied back into dist/.

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
APP_NAME="Stava Player"
DMG_NAME="${DMG_NAME:-$APP_NAME-mac.dmg}"
BUILD_ROOT="${BUILD_ROOT:-$HOME/Library/Caches/stava-player-build}"

# Prefer the bundle still sitting in the build root. The copy under dist/ gets
# com.apple.FinderInfo stamped onto its framework directories by iCloud within
# seconds of being written, and packaging that copy carries the attribute into
# the image, where `codesign --verify --strict` then rejects it.
if [[ -z "${APP_BUNDLE:-}" ]]; then
  if [[ -d "$BUILD_ROOT/dist/$APP_NAME.app" ]]; then
    APP_BUNDLE="$BUILD_ROOT/dist/$APP_NAME.app"
  else
    APP_BUNDLE="$DIST_DIR/$APP_NAME.app"
  fi
fi
STAGING_DIR="$BUILD_ROOT/dmg-root"
DMG_BUILD_PATH="$BUILD_ROOT/$DMG_NAME"

if [[ ! -d "$APP_BUNDLE" ]]; then
  echo "App bundle not found: $APP_BUNDLE" >&2
  exit 1
fi

mkdir -p "$BUILD_ROOT"
rm -rf "$STAGING_DIR" "$DMG_BUILD_PATH"
mkdir -p "$STAGING_DIR"
echo "[create_dmg] Packaging: $APP_BUNDLE"
cp -R "$APP_BUNDLE" "$STAGING_DIR/"
ln -s /Applications "$STAGING_DIR/Applications"

# Belt and braces: strip anything a file provider may have attached to the copy.
xattr -cr "$STAGING_DIR/$APP_NAME.app" 2>/dev/null || true

hdiutil create \
  -volname "$APP_NAME" \
  -srcfolder "$STAGING_DIR" \
  -ov \
  -format UDZO \
  "$DMG_BUILD_PATH"

rm -rf "$STAGING_DIR"

mkdir -p "$DIST_DIR"
cp "$DMG_BUILD_PATH" "$DIST_DIR/$DMG_NAME"

echo "[create_dmg] Created: $DIST_DIR/$DMG_NAME"
