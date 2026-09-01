#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
SPEC_FILE="${SPEC_FILE:-$ROOT_DIR/Stava Player mac.spec}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python executable not found: $PYTHON_BIN" >&2
  exit 1
fi

cd "$ROOT_DIR"

echo "[build_mac] Using Python: $PYTHON_BIN"
echo "[build_mac] Using spec: $SPEC_FILE"

"$PYTHON_BIN" -m PyInstaller --noconfirm "$SPEC_FILE"

echo "[build_mac] Build complete: $ROOT_DIR/dist/Stava Player.app"