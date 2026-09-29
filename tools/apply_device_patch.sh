#!/usr/bin/env bash
# Translate an updated, non-rooted Android install of HOK ACE (com.tencent.tmgp.osgame).
#
# Usage (from the translator folder, Git Bash):  bash tools/apply_device_patch.sh
#
# Flow: install debuggable APK (for run-as file access) -> pull QtsVFS packages ->
# build English packages -> push them back -> clear Watchdog -> reinstall normal APK.
# The game must already be fully updated with "hok ace mobile resigned.apk" before running.
set -euo pipefail
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/.." && pwd -W 2>/dev/null || pwd)"
ADB="$ROOT/apk-editor-studio_windows_1.7.2/APK Editor Studio v1.7.2/tools/adb.exe"
PY="${PY:-$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe}"
PKG=com.tencent.tmgp.osgame
STAMP="$(date +%Y%m%d-%H%M%S)"
WORK="$ROOT/work/device-$STAMP"
GAME="$WORK/game"

"$ADB" get-state >/dev/null
"$ADB" shell am force-stop "$PKG"

echo "== install debuggable APK (temporary, game cannot run with it)"
"$ADB" install -r "$ROOT/hok ace mobile debuggable.apk" | tail -1

echo "== pull packages and Watchdog"
mkdir -p "$GAME/WXQ_Data/Package"
"$ADB" exec-out run-as "$PKG" tar -cf - -C files/QtsVFSCache packages Watchdog > "$WORK/device-backup.tar"
tar -xf "$WORK/device-backup.tar" -C "$GAME/WXQ_Data/Package" packages
# The scanner reads numeric package folders from WXQ_Data/Package/builtin.
mv "$GAME/WXQ_Data/Package/packages" "$GAME/WXQ_Data/Package/builtin"

echo "== build English packages"
(cd "$ROOT/work" && PYTHONPATH="vendor;../tools" "$PY" ../tools/build_device_patch.py \
    --runtime patcher-pyz --game "$GAME" --catalog patcher-extracted/catalog \
    --work "$WORK/build" --output "$WORK/staged")

echo "== push packages"
"$ADB" shell "rm -rf /data/local/tmp/hok && mkdir -p /data/local/tmp/hok"
for dir in "$WORK/staged"/*/; do
    id="$(basename "$dir")"
    case "$id" in *[!0-9]*) continue ;; esac
    "$ADB" shell "mkdir -p /data/local/tmp/hok/$id"
    "$ADB" push "$dir". "/data/local/tmp/hok/$id/" | tail -1
    "$ADB" shell "chmod -R 755 /data/local/tmp/hok; run-as $PKG sh -c 'cp /data/local/tmp/hok/$id/* files/QtsVFSCache/packages/$id/'"
done
"$ADB" shell "run-as $PKG sh -c 'rm -rf files/QtsVFSCache/Watchdog/*'; rm -rf /data/local/tmp/hok"

echo "== reinstall normal APK"
"$ADB" install -r "$ROOT/hok ace mobile resigned.apk" | tail -1
echo "Done. Backup of the original device data: $WORK/device-backup.tar"
