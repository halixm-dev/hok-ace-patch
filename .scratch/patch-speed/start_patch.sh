#!/bin/sh
# Start one patch run on the phone from the patcher's home screen, then confirm its dialog.
# usage: start_patch.sh <logcat capture file>
log="$1"
dev="adb -s ebad528e"
center() {  # center of the first clickable node whose text starts with $1
  $dev shell "uiautomator dump /sdcard/ui.xml >/dev/null; cat /sdcard/ui.xml; rm /sdcard/ui.xml" |
    tr '>' '\n' | grep -F "text=\"$1" | grep -o 'bounds="[^"]*"' | head -1 |
    sed -E 's/bounds="\[([0-9]+),([0-9]+)\]\[([0-9]+),([0-9]+)\]"/\1 \2 \3 \4/' |
    awk '{ printf "%d %d", ($1+$3)/2, ($2+$4)/2 }'
}
$dev shell "am start -n dev.halixm.hokacepatcher/.MainActivity >/dev/null"; sleep 3
$dev shell 'pidof com.tencent.tmgp.osgame' && { echo "game is running; refusing"; exit 1; }
$dev shell 'head -c 22 /sdcard/Android/data/com.tencent.tmgp.osgame/files/Cache/Update/NewVersionInfo.json'; echo
for label in "Start another patch" "Start" "Try again"; do
  xy=$(center "$label"); [ -n "$xy" ] && { echo "tap $label at $xy"; $dev shell "input tap $xy"; break; }
done
[ -z "$xy" ] && { echo "no start button"; exit 1; }
for i in $(seq 1 120); do
  xy=$(center "All in-game updates finished"); [ -n "$xy" ] && break
  grep -q '"status":"error"' "$log" && { grep 'Result:' "$log" | tail -1; exit 1; }
  sleep 5
done
[ -z "$xy" ] && { echo "no confirmation dialog"; exit 1; }
$dev shell "input tap $xy"; sleep 1
xy=$(center "START PATCH"); $dev shell "input tap $xy"; sleep 3
grep 'Start command patch' "$log" | tail -1 | cut -c1-120
