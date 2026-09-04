#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
DMG_PATH="${DMG_PATH:-$DIST_DIR/Stava Player-mac.dmg}"
KEYCHAIN_PROFILE="${NOTARY_PROFILE:-}"
APPLE_ID="${APPLE_ID:-}"
APPLE_TEAM_ID="${APPLE_TEAM_ID:-}"
APPLE_APP_PASSWORD="${APPLE_APP_PASSWORD:-}"

if [[ ! -f "$DMG_PATH" ]]; then
  echo "DMG not found: $DMG_PATH" >&2
  exit 1
fi

if [[ -n "$KEYCHAIN_PROFILE" ]]; then
  xcrun notarytool submit "$DMG_PATH" --keychain-profile "$KEYCHAIN_PROFILE" --wait
else
  if [[ -z "$APPLE_ID" || -z "$APPLE_TEAM_ID" || -z "$APPLE_APP_PASSWORD" ]]; then
    echo "Provide NOTARY_PROFILE or APPLE_ID + APPLE_TEAM_ID + APPLE_APP_PASSWORD." >&2
    exit 1
  fi
  xcrun notarytool submit "$DMG_PATH" \
    --apple-id "$APPLE_ID" \
    --team-id "$APPLE_TEAM_ID" \
    --password "$APPLE_APP_PASSWORD" \
    --wait
fi

xcrun stapler staple "$DMG_PATH"
spctl --assess --type open --context context:primary-signature -v "$DMG_PATH"

echo "[notarize_mac] Notarization and stapling complete."