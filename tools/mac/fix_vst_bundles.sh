#!/usr/bin/env bash
set -euo pipefail

# PyInstaller splits every nested .vst / .vst3 bundle in two: the Mach-O binary
# stays under Contents/Frameworks, everything else is moved to Contents/Resources,
# and the two halves are wired back together with symlinks. Neither half is a
# signable bundle afterwards - the Frameworks copy has a symlinked Info.plist and
# the Resources copy has a symlinked MacOS - so codesign refuses the whole app
# with "the main executable or Info.plist must be a regular file (no symlinks)".
#
# This flattens each plugin back into one real bundle under Frameworks, drops the
# now-redundant Resources half, and signs the plugins so the outer app can be
# signed afterwards. Run it after build_mac.sh and before signing.

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
APP_BUNDLE="${APP_BUNDLE:-$ROOT_DIR/dist/Stava Player.app}"
IDENTITY="${MACOS_SIGN_IDENTITY:--}"

if [[ ! -d "$APP_BUNDLE" ]]; then
  echo "App bundle not found: $APP_BUNDLE" >&2
  exit 1
fi

FW_VST_DIR="$APP_BUNDLE/Contents/Frameworks/libs/VST"
RES_VST_DIR="$APP_BUNDLE/Contents/Resources/libs/VST"

if [[ ! -d "$FW_VST_DIR" ]]; then
  echo "[fix_vst] No VST directory under Frameworks; nothing to do."
  exit 0
fi

# Each plugin dir is name-mangled by PyInstaller (Wider.vst -> Wider__dot__vst)
# with a Wider.vst symlink beside it; the app resolves the symlink at runtime,
# so the mangled directory is the real bundle and the one we must repair.
while IFS= read -r bundle; do
  [[ -d "$bundle" ]] || continue
  contents="$bundle/Contents"
  [[ -d "$contents" ]] || continue

  echo "[fix_vst] Flattening $(basename "$bundle")"

  # Replace every symlinked entry with a real copy of what it points at.
  for entry in "$contents"/*; do
    [[ -L "$entry" ]] || continue
    name="$(basename "$entry")"
    tmp="$contents/.fix_vst_tmp_$name"
    rm -rf "$tmp"
    cp -RL "$entry" "$tmp"   # -L dereferences the symlink
    rm -f "$entry"
    mv "$tmp" "$entry"
  done

  # The bundled signature no longer matches: PyInstaller thins the universal
  # binary down to the target arch, which invalidates the vendor's signature.
  rm -rf "$contents/_CodeSignature"

  # Restore the real bundle name. PyInstaller mangles the dot (Wider.vst ->
  # Wider__dot__vst) and leaves a Wider.vst symlink pointing at it, but codesign
  # only treats a directory as a bundle when the name itself carries the
  # extension - otherwise it descends into it and chokes on PkgInfo with
  # "code object is not signed at all". Replacing the symlink with the real
  # directory keeps the runtime lookup working and makes it signable.
  real_name="$(basename "$bundle" | sed 's/__dot__/./')"
  target="$(dirname "$bundle")/$real_name"
  rm -f "$target"          # the symlink PyInstaller left behind
  mv "$bundle" "$target"

  codesign --force --timestamp --sign "$IDENTITY" "$target"
done < <(find "$FW_VST_DIR" -maxdepth 2 -type d \( -name '*__dot__vst' -o -name '*__dot__vst3' \))

# The Resources half of the Mac plugins only existed to feed those symlinks. Its
# MacOS entry is a symlink, which would make it an unsignable bundle, and nothing
# reads from it - the app resolves plugins relative to Frameworks (sys._MEIPASS).
# Only the Mac subtree goes: Frameworks/libs/VST/Windows is itself a symlink into
# Resources, so removing more than this would leave a dangling link behind.
if [[ -d "$RES_VST_DIR/Mac" ]]; then
  echo "[fix_vst] Removing redundant Resources/libs/VST/Mac"
  rm -rf "$RES_VST_DIR/Mac"
fi

echo "[fix_vst] Done."
