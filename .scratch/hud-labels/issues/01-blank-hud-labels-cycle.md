# 01: Why the in-match HUD button labels draw blank in English

Status: ready-for-human
Type: research

**Symptom (user, 2026-10-29, 1.8.0.1):** in a match, the labels under the HUD buttons (设置, 阵容, 全局 top
left; 统计, 天赋, 聊天 top right) show in Chinese but are empty in English. The icons draw; the text does not.

**What the data says.** The labels are rows of the HUD button table `08B61ADA9E913D68` (package `1`,
prime-only, catalogued, reaches the override layer through the append pass). The shipped catalog translates
all 55 of its rows (`translate_table`: 55/55), and the staged copy reads back with them. So the English
reaches the phone; it is the drawing that fails. Two causes fit:

1. the label's font holds only the Chinese characters it needs, so Latin letters draw as nothing;
2. the label box is sized for two Chinese characters and drops text that does not fit.

"Chat" is blank too, which points at (1), but it does not prove it.

**The probe.** The runtime refuses a translation that still holds Chinese (`still_chinese`), so a mixed
"聊天Chat" stays Chinese and cannot be the probe. Instead, one run with a probe catalog
(`dist\HOK ACE Patcher Data\probe-catalog-hud`, the shipped English catalog with two entries changed):

- `聊天` removed: the Chat label stays Chinese, proving the table reaches the screen;
- `设置` → `S`: one Latin letter, which fits any box.

Built offline on 2026-10-29 against `pristine/20261029-1.8.0.1` + `installed.apk`
(`dist\HOK ACE Patcher Data\probe-hud-out`, log `probe-hud-build.log`): exit 0, 287 tables added from the
APK, the usual `3A70308AAF6F18F8` encoder refusal. The staged `08B61ADA9E913D68` reads back with `聊天`
Chinese, the `设置` row as `S`, the rest English.

**Run it** (`docs/runbooks/device-cycle.md`, steps 1 and 3–9): confirm the phone's
`files/QtsVFSCache/packages/1/1.info` names 1.8.0.1, back up `packages` and `Watchdog`, push every package
folder of `probe-hud-out`, reinstall the normal APK, log in, start a match and screenshot the top HUD.

| Chat label | Settings label | Verdict |
|---|---|---|
| 聊天 | blank | the font has no Latin letters; a text fix cannot reach it |
| 聊天 | S | the box is too small for the English; try shorter labels |
| blank | — | the table does not feed these labels; look for another source |

Afterwards, patch again with the normal patcher (or restore `backup.tar`): the probe leaves Settings as
"S" and Chat in Chinese everywhere those strings appear.

## Comments

**2026-10-29, pushed to `f15a72e`.** Phone `packages/1/1.info` 1.8.0.1 = dump; `needDownloadSize` 0 (the
file is under `/storage/emulated/0/Android/data/…/files/Cache/Update/`, not `files/Cache/Update/`); the
installed APK's SHA-256 `29b3ee7e…defdc` = the cached `installed.apk`, launcher label already English.
Backup `dist\HOK ACE Patcher Data\probe-hud-backup.tar` matches the phone: 775 files, 3,288,563,887 bytes,
sizes equal file by file. Pushed the 14 `.db` files of `probe-hud-out` (7 packages), each SHA-256 equal on
the phone; Watchdog cleared; normal APK reinstalled (same SHA). Roll back by restoring the backup, not by a
fresh patch run: the patcher's pristine delta expects the layer the backup holds. Verdict pending the
user's match screenshot.

**2026-10-29, verdict (user): all blank.** Chat and Settings both draw nothing, as do the other four. So
`08B61ADA9E913D68` does not feed these labels: its `聊天` row was Chinese and still did not show. The probe
catalog also left `聊天` Chinese in every other catalog table, so no text table that holds a bare `聊天`
feeds the label either; a label read from one would have shown Chinese. No catalog texture names these
labels. Phone still on the probe; restore `probe-hud-backup.tar` once the user has stopped playing.

**2026-10-29, what draws the labels.** The button configs `F06E1F69C614325B` (keys `#AD5D…#`) and
`1DCCAE00A5377B52` (`#31AA…#`), both prime-only and uncatalogued, map each HUD button to a label key and a
tip key in `08B61ADA9E913D68` / `CD0C563390211E01` (`…C57DEDC1ABD8` → 统计, tip `…C39A6C6891FB`). So the
labels do read these tables, and a Chinese `聊天` still drew blank: the appended copies themselves may be
what fails. Their staged bytes keep every key in order; only the values change.

**Probe 2, built.** `probe-catalog-hud2` is the shipped catalog with those two hashes dropped from
`table_hashes`, so the append leaves the game's own copies in place: `probe-hud2-out`, exit 0, 285 tables
added from the APK (287 − 2), neither table staged. Labels Chinese → the appended copies break them;
still blank → another part of the patch does.

**2026-10-29, probe 2 pushed, USB unstable.** The phone dropped off adb twice mid-run. After the first
drop all 14 files on the phone hashed equal to `probe-hud2-out` (the copy had finished). The Watchdog clear,
the `/data/local/tmp/hokace` cleanup and the normal-APK reinstall are still owed: the phone went offline
with the **access APK installed**, so the game must not be launched until the normal APK is back.
After `adb reconnect offline`: Watchdog cleared (0 entries), temp folder gone, normal APK reinstalled
(SHA-256 `29b3ee7e…defdc`, `run-as` now refused, so the access APK is gone).

**2026-10-29, probe 2 verdict (user): still blank.** The game's own copies of the two label tables do not
bring the captions back, so the appended tables are not the cause. On a closer read, `F06E1F69C614325B` is
the keyboard-shortcut hint config (shop, main view, switch view…), not the captions: bare `阵容` and `全局`
are not in it. No catalog texture is a HUD icon (the 22 non-card textures are rank badges and lobby
buttons). And no in-game option hides button captions.

**Probe 3, built.** Suspect: the line-break reset, `SCRIPT_EDITS[0x3482BF89614B5ABB]`
(`TextRendering.SetFlag(false)` on every `UIPrefabClass:Create`), which changes how every label is laid
out and fits a caption vanishing whatever its text. `probe-hud3-out` is the shipped catalog with only that
edit left out (scratchpad wrapper around `build_device_patch.main`). Captions back → the reset blanks them;
still blank → look at the remaining script edits and the appended Lua.
Build: exit 0; package 10 adds 1 script from the APK instead of 2. Against probe 1, packages 1 (probe 1's
catalog edits) and 10 differ as expected, and package 19 differs in one asset only, `13C19E4E4486B31C`,
the rank-badge atlas, which is encoded fresh each run (ASTC encoder variation, not this change).
Pushed 2026-10-29 to `f15a72e` (after `adb reconnect offline`): 14 files, every SHA-256 equal on the phone;
Watchdog cleared, temp folder gone, normal APK reinstalled (`29b3ee7e…defdc`, `run-as` refused).

**2026-10-29, probe 3 verdict (user): still blank.** The line-break reset is not the cause. Three
targeted probes have missed, so the next cycle is the control: the dump's own pristine files for the
seven packages the patch writes (`pristine/20261029-1.8.0.1`, same APK SHA-256), a fully Chinese game.
Captions show → the patch blanks them, bisect by package; still missing → the patch is not involved.
Pushed 2026-10-29: the 14 pristine `.db` files, every SHA-256 equal on the phone; Watchdog cleared, normal
APK reinstalled (`29b3ee7e…defdc`, `run-as` refused).

**2026-10-29, control verdict (user): still blank, in Chinese.** With every package the patch writes back
at its pristine bytes, the captions are still missing. The patch does not cause this: neither the text,
the textures nor the script edits. What is left differs between the user's game and the Chinese reference
screenshot outside the override layer (an account or server-side switch, a setting, the layout, or the
re-signed APK). Not a translation defect; nothing for either patcher to fix until a Chinese screenshot
from this phone, unpatched, shows the captions.

**2026-10-29, restored.** `probe-hud-backup.tar` pushed (SHA-256 `9fdb1e20…ddccf` equal on the phone) and
extracted over a cleared Watchdog: 775 files, sizes equal file by file, nothing extra; the 14 files the
probes wrote hash equal to the backup's. Normal APK reinstalled (`29b3ee7e…defdc`, `run-as` refused).
The probe catalogs, builds, logs and the backup were then deleted from `dist\HOK ACE Patcher Data` (user).
