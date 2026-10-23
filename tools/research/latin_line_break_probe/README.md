# Latin line-break probe (throwaway)

Research record for [latin-line-breaks](../../../docs/features/latin-line-breaks.md): the two probes that found
the line-break flag and the reset that fixed it, with their device evidence in `evidence/`. Nothing imports it.

A device cycle that answers one question: **is `TextRendering`'s flag on, and does turning it off make the
Card screen wrap English at spaces?** It is a diagnostic build, never a release. Nothing under `tools/`
changes: `build_probe.py` adds `probe.lua` to the `PVPRankDataClass` script edit (`6CB505C6553141B4`,
package `10`) in memory, then runs the normal `build_device_patch`.

## What the probe does

The first time the lobby draws a rank title (`vGetRankTitle`), the probe:

1. Logs whether `CS.UnityEngine.TextRendering` and its `SetFlag` are reachable from xLua.
2. Takes the font of the first active `UI.Text` and lays out one English sentence with a fresh
   `TextGenerator` at three widths. Each layout is logged as its lines plus a `midword` count (breaks with a
   letter on both sides).
3. Calls `SetFlag(true)` and lays the sentence out again, then calls `SetFlag(false)` and lays it out again.
   It leaves the flag **off** for the rest of the session.

Everything runs inside `pcall`, so a failure is logged and the game carries on. The log is appended to
`/sdcard/Android/data/com.tencent.tmgp.osgame/files/latin_line_break_probe.txt`. It also goes to `print`,
which may reach logcat. A `---- script loaded` line is written when the script loads, so a missing probe
section means `vGetRankTitle` never ran, not that the edit failed to land.

## Build

Built 2026-10-23 against the 1.7.0.2 pristine snapshot and the cached APK:

```bat
.venv\Scripts\python.exe tools\research\latin_line_break_probe\build_probe.py --runtime resources\runtime ^
    --game "dist\HOK ACE Patcher Data\pristine\20261023-1.7.0.2\game" --catalog resources\catalog ^
    --work D:\scratch\latin-line-breaks\work-probe --output D:\scratch\latin-line-breaks\out-probe ^
    --apk "D:\HOK ACE Patcher Data\cache\HOK ACE Patcher Data\installed.apk"
```

The control build, `D:\scratch\latin-line-breaks\out-control`, is the same command through
`tools\build_device_patch.py`. Both builds exit 0 with identical summaries apart from package `10`, and
only `10/10.db` and `10/10_0.db` differ between the outputs. Read back through `QtsPackage` (with
`install_btree_slot_map()`), the staged `6CB505C6553141B4` is 38 415 bytes in `out-probe` (32 227 in
`out-control`). It holds the probe and both rank-title edits, and compiles under Lua 5.3. Before the
build, the probe ran against a mocked engine in Lua 5.3: once with working calls (flag on: `midword` 2, flag
off: 0, run once only), and once with `SetFlag` and `FindObjectsOfType` throwing (logged, no escape).

## On the phone

Follow `docs/runbooks/device-cycle.md`. Notes for this cycle:

- **Step 1–2:** the phone's `files/QtsVFSCache/packages/1/1.info` must still read data `1.7.0.2`. If the game
  has updated since, rebuild both outputs from a fresh snapshot first.
- **Step 5:** push every package directory in `out-probe` (the probe build is the full English patch plus the
  probe), not only `10`.
- **Step 8–9:** log in and wait for the lobby, so the rank title is drawn. Then pull the log:

  ```bat
  adb pull /sdcard/Android/data/com.tencent.tmgp.osgame/files/latin_line_break_probe.txt
  ```

  Then open the **Card** screen and screenshot a card description that used to split a word (for example
  "Ancient Coi n").
- **Roll back:** run the patcher normally, or push `out-control` the same way. The flag is set only in memory,
  so a game restart without the probe restores the engine's own state.

## Reading the result

| Log shows | Meaning |
|---|---|
| `before` lines equal the `flag=true` lines, with `midword` > 0 | The flag was on at startup; lever 1 (`SetFlag(false)`) or lever 2 (`NumberCharacters`) can fix it. |
| `before` lines equal the `flag=false` lines | The flag was already off. If the Card screen still splits words, card text does not come from this generator. |
| `SetFlag(...): error` | No compiled body; lever 1 is out, lever 2 remains. |
| `TextRendering type: nil` | xLua cannot reach the class; lever 1 is out. |
| `flag=true` and `flag=false` lines identical | The flag does not change this generator's layout; re-read the static notes. |

Whatever it shows, the Card screenshot with the flag off is the screen evidence. Record the verdict in
`docs/lab-notebook.md` before the next cycle.

## Probe v2

Probe v1 showed the flag comes back on within a session. `build_probe.py --v2` puts `probe_v2.lua` into
`UIPrefabClass` (`3482BF89614B5ABB`, prime-only, carried by the append pass). On every
`UIPrefabClass:Create`, before the prefab initialises, it does three things:

1. Lays the sample out at a narrow width to read the flag (`on` when a break falls inside a word).
2. Calls `SetFlag(false)`.
3. Appends `n  clock  state  class  path` to `files/latin_line_break_probe_v2.txt`.

A line marked `<<< flag was ON` means the flag was turned on since the previous create. The log stops at
2000 creates; the reset continues.

Built 2026-10-23 to `D:\scratch\latin-line-breaks\out-probe-v2`. It differs from `out-control` only in
package `10`, which was pushed alone (`10.db` `5b531cd2…`, `10_0.db` `47d3f05d…`). The staged `UIPrefabClass`
is 45 821 bytes and compiles. Pull the log with:

```bat
adb pull /sdcard/Android/data/com.tencent.tmgp.osgame/files/latin_line_break_probe_v2.txt
```
