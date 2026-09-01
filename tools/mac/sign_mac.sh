#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
APP_BUNDLE="${APP_BUNDLE:-$DIST_DIR/Stava Player.app}"
DMG_PATH="${DMG_PATH:-$DIST_DIR/Stava Player-mac.dmg}"
IDENTITY="${MACOS_SIGN_IDENTITY:-}"
ENTITLEMENTS_FILE="${ENTITLEMENTS_FILE:-}"

if [[ -z "$IDENTITY" ]]; then
  echo "Set MACOS_SIGN_IDENTITY to your Developer ID Application identity." >&2
  exit 1
fi

if [[ ! -d "$APP_BUNDLE" ]]; then
  echo "App bundle not found: $APP_BUNDLE" >&2
  exit 1
fi

SIGN_ARGS=(--force --deep --options runtime --timestamp --sign "$IDENTITY")
if [[ -n "$ENTITLEMENTS_FILE" ]]; then
  SIGN_ARGS+=(--entitlements "$ENTITLEMENTS_FILE")
fi

codesign "${SIGN_ARGS[@]}" "$APP_BUNDLE"
codesign --verify --deep --strict --verbose=2 "$APP_BUNDLE"

if [[ -f "$DMG_PATH" ]]; then
  codesign --force --timestamp --sign "$IDENTITY" "$DMG_PATH"
  codesign --verify --verbose=2 "$DMG_PATH"
fi

echo "[sign_mac] Signing complete."