# Repatch without clearing the game's data

Status: needs-triage

Tickets: [`issues/`](issues/) 01–08. Settled through grilling rounds 1–4 (2026-10-17).

## Problem

A phone that is already translated cannot be patched again without clearing the game's data. Clearing
costs a ~2.7 GB re-download and a login. Three cases hit this, and the first is the one users hit most:

1. **After an in-game update.** The update brings back Chinese text, or the repatch fails or the game
   force-closes, and the user has to clear before the patcher works again.
2. **A newer translation** of the data already on the phone (a catalog fix, a newly covered string).
3. **A language switch**, English to Indonesian or back.

The cause is the text pass: it translates only records that are still Chinese. Over an English install
the Indonesian catalog changes 0 of 387 tables, while the textures would still switch, which leaves
MULAI GAME over English text ([indonesian-language](../../docs/features/indonesian-language.md), Report,
language-switch row). The patcher keeps no copy of the pristine bytes it overwrote, so clearing is the
only way it can get the Chinese source back. Both pickers and `README.md` tell the user to clear first.

## Evidence

Lab notebook, 2026-10-17, "Reverse delta from a staged layer back to the pristine one": an English
build over the pristine 1.6.0.1 snapshot stages 14 `.db` files (925.7 MB of pristine bytes). Every
staged file is its pristine file with ranges overwritten in place (6.14 MB, almost all `1/1_0.db`) and
data appended past the pristine end (83.36 MB). The pristine bytes of the overwritten ranges, plus each
pristine length, rebuild all 14 originals byte-for-byte, and come to **5.12 MB** zlib-compressed,
against 898.3 MB for compressed full copies. The Indonesian build stages the same 14 files; its delta is 3.87 MB
and also round-trips. The two languages overwrite different ranges of `1/1_0.db`, which is why a delta
is always made against pristine, never against the previous install.

## Solution

After each install, the patcher keeps a **pristine delta**: for every package file it wrote, the
pristine bytes of the ranges it overwrote and the pristine length. On a later run, the patcher checks
which files the delta names still hold the bytes the last install wrote, rebuilds the pristine files
from them and the delta in its own local copy of the layer, and builds the new language from that. For
a language switch or a newer translation, the phone receives one write per staged file, exactly as a
normal install does, and nothing pristine is pushed back. Only the update flow writes pristine bytes
to the phone.

A run whose check fails stops before any game file is written and tells the user to clear the game's
data. (The check reads the pulled files, and the pull itself needs the access APK, so a refused run
still installs the access APK and puts the normal one back, as a run with nothing to change does.) After an in-game update, the run uses the [Game updates](#game-updates) flow instead.

## Implementation Decisions

- **One shared module, `tools/pristine_delta.py`.** `make(pristine_dir, staged_dir) -> Delta`,
  `write(delta, path)` / `read(path)`, and `rebuild(layer_dir, delta, out_dir)`. The Windows front end
  calls it from `patcher_core`; Android calls it through `android_bridge`. No Kotlin reimplementation:
  the delta is made and applied by the engine both front ends already ship.
- **Delta format.** One file per install, schema-versioned JSON header plus a zlib body. Per package
  file: its path relative to `packages/`, the pristine length and SHA-256, the staged length and
  SHA-256, and the overwritten ranges as `(offset, length)` with their pristine bytes. A file the patch
  created (none today) records pristine length 0 and rebuilds as deleted.
- **Range detection.** Compare in 4 KiB blocks, then 64-byte sub-blocks inside a changed block, and
  coalesce changed runs closer than 256 bytes (the measured parameters). Always read both files whole
  from disk, never from in-memory staging state, so the delta describes the bytes actually written.
- **The delta always points at pristine.** When a run starts from a rebuilt pristine layer, its new delta is
  made against the rebuilt pristine files, not against the previous install. Each patcher keeps one
  delta; there is no chain.
- **Valid per file, not per data version.** A file's entry stays valid exactly while that file holds
  the staged SHA-256 the entry records; the data version is recorded only for the log, because an
  update can change content under an unchanged `1.info` (lab notebook, 2026-10-10). After an update, the
  entries for the files it left alone stay usable.
- **Self-verifying.** `rebuild` takes a file only when its length and SHA-256 equal the entry's
  staged values, and verifies each rebuilt file against the pristine SHA-256 before the build reads it.
  A file whose bytes match neither the entry's staged nor its pristine values goes to the update flow's
  rules ([Game updates](#game-updates)); when no rule accepts it, the run raises a `PatchError` that
  says to clear the game's data, before any game file is written, so a refused run never changes the
  game's data.
- **When a delta is made.** Only after the install is verified complete: Windows after
  `push_translation`, Android after `GameFileTransaction.finishApply`. It is written atomically and
  replaces the previous one only once it is durable. An interrupted install keeps the old delta, which
  still describes the layer: rollback restores those bytes.
- **Bootstrapping a delta on the Windows patcher.** When it holds no delta, it tries once to build
  one from a kept session (it keeps the last two): that session's `device-backup.tar` must pass the
  round-1 pristine signals, and the phone's files must equal that session's staged output. Then a
  phone patched before this ships needs no clear.
- **When a run may make the first delta.** Only from a pristine layer, judged by two signals together,
  because the game carries no per-file pristine hash (`.info` holds only version and revision;
  `pkgHash` is not content-derived; the row-checksum MD5s cover only config bins, which the patch never
  rewrites):
  - no pulled file's SHA-256 equals a staged hash this patcher has ever recorded (each patcher keeps
    the staged hashes of every install it made), and
  - the run's text pass translated records in every text table it staged.

  A layer patched by an older patcher version, or by the other front end, fails the second signal. The
  run then stops with the clear-data message.
- **Where it lives: with each patcher.** Windows: `<working folder>/pristine/delta.bin`.
  Android: `filesDir/pristine/delta.bin`, outside `sessions/`, so `releaseSession` never reclaims it.
  A delta is never
  shared between the Windows patcher and the Android patcher: a phone patched by one and then run
  through the other has no delta there, and the run says to clear the game's data and download again,
  or to patch with the patcher that patched it last.
- **Build input on Android.** `snapshot/` must keep the phone's actual bytes, because rollback writes
  them back. The rebuilt pristine files go into a separate build-input copy of only the files the delta
  names (~0.9 GB), with the rest of the layer read from `snapshot/`. `build_storage.estimate` reserves
  that copy.
- **Windows build input.** `pull_game_data` already extracts its own copy into
  `sessions/<stamp>/game`; `rebuild` rewrites the named files there in place. `device-backup.tar` keeps
  the phone's actual bytes.
- **Front ends.** Both pickers and `README.md` stop saying to clear before switching when the patcher
  holds a delta for the phone; the run log names which path it took (`rebuilt N files from the
  pristine delta` or the reason it could not).
- **Vocabulary.** **Pristine layer** and **Pristine delta** are in `GLOSSARY.md`.

- **Decided while implementing 02–05 (2026-10-17), for the spec owner to confirm:**
  - A file the last install translated and the new build no longer stages goes back to the phone at
    its rebuilt pristine bytes; otherwise it would keep the old language. No case today (both languages
    stage the same 14 files).
  - Windows writes the new delta as `delta.pending.bin` before the first push and makes it the delta
    after the last, because a cut-off push has no rollback; the next run accepts either delta's staged
    bytes per file. Android makes the delta during the build and promotes it once the run is
    `COMPLETE`. Neither keeps a delta for an install that did not finish.
  - A delta that does not match while no file is at a staged hash this patcher recorded is stale (the
    data was cleared, possibly onto a newer version): the run builds as a first install under the text
    signal. Without this, the clear the refusal asks for would be refused again.
  - The text signal is `pristine_delta.text_not_pristine`: the tables the text pass planned equal
    `counts["tables"]`, the catalog tables it read.

## Testing

- Offline round trip, no device: for English and Indonesian builds over the pristine 1.6.0.1 snapshot,
  `rebuild` over the staged layer reproduces every pristine SHA-256. A `tools/research/` check.
- Offline switch: English stage, then `rebuild` + Indonesian build from the result; its staged files
  are byte-identical to an Indonesian build straight from the pristine snapshot. The same for
  Indonesian then English, and for English then English (a rerun).
- Refusals: a named file one byte different, one truncated, one missing, and a layer patched by the
  other patcher each refuse with the clear-data message before
  any game file is written.
- Device cycle ([device-cycle](../../docs/runbooks/device-cycle.md)): English install, then switch to
  Indonesian without clearing; the lobby reads MULAI GAME with Indonesian text, no in-game repair runs,
  and the login survives. Then switch back to English.

## Game updates

In scope. The update flow is built only after the first ticket measures it on a phone; the language
switch and the newer-translation case do not depend on the updater and ship first.

**Decided (grilling round 2):**

- **One Start Patch flow.** The user never needs to know an update is coming. A run that finds an
  update pending or failed writes the pristine bytes back to the patched files the update needs, tells
  the user to open the game, let the update finish to the login screen and close it, waits for their
  confirmation, then patches in the same run.
- **The pristine write-back is the one write ADR 0002 allows before an update** (its Consequences).
- **First ticket: a device cycle at the next real game update**, on a patched phone. It saves
  `QtsVFS.log`, `normal1.log`, `Watchdog` and the layer before and after the update; then, after a
  clear and repatch (or on a second patched phone), it writes the pristine bytes back before the update
  and compares the outcome. Old pristine data cannot be staged offline: the only older local layer,
  `grid-regression/old-patched-game`, is already patched.

- **A file the update replaced** (bytes matching neither the entry's staged nor its pristine values)
  becomes that file's new pristine when the round-1 signals hold for it: its SHA-256 is not one this
  patcher ever staged, and the text pass finds Chinese in every text table it stages from it. A file
  that fails them, such as one the repair left half Chinese and half English, refuses the run with the
  clear-data message. Revisit once the first ticket shows what a real update leaves.
- **When the update flow starts.** On an already-patched phone, when any of these holds: (i) a file the
  delta names changed since the install; (ii) `Watchdog/History.db` has merge events dated after the
  install; (iii) the user answers yes to "Did the game update, crash, or show Chinese text since the
  last patch?", asked only when (i) and (ii) are both quiet.
- **Write-back scope.** Every file still at its staged hash gets its pristine bytes back; which ones a
  given update diffs is not knowable beforehand, and the write is the size of a normal install.
- **Two access cycles in one run.** The game must not open while the access APK is installed (a
  debuggable build dies on launch, lab notebook §2 Cause B), so the run goes: access APK, pristine
  write-back, normal APK, the user updates the game, access APK, pull and build, translation write,
  normal APK.
- **Remove translation.** Both patchers gain an action that writes the pristine bytes back with no new
  patch, through the same transaction as the update flow's write-back, and leaves the phone with no
  valid delta entries to rebuild from (its files are pristine). The re-signed normal APK stays installed:
  neither patcher keeps Tencent's own signed APK, so the screen says to keep using Scan to login and to
  reinstall from the store for the official app.

**What is known, and how well:**

- **Inferred from `QtsVFS.dll` and the 10-16 Watchdog (research, 2026-10-17):** an update merges diffs
  into a package in place, asset by asset. Each asset is checked against the CRC the package stores for
  it (`PreCheck hdiff src crc mismatch`, then `dest crc mismatch`), and the diff's source package hash
  must equal the package's current hash. `History.db` logged 88 packages merged through 1–7 diffs; the
  other 126 had no merge record, so they were probably downloaded whole. Our writes leave a package's hash and
  each asset's stored token unchanged while its bytes are ours, so a diff aimed at a patched asset
  fails on the bytes. The repair path (`BrokenList` → `QtsfFixer::FixFile`) restores assets one at a
  time against their stored CRCs, which would bring the Chinese text back.
- **Not measured in this repo:** `errorCode:361` and the "binary diff" wording in
  [ADR 0002](../../docs/adr/0002-write-the-translation-after-the-in-game-update.md) come from the upstream
  PC patcher's README; no updater log of a failed diff was ever saved. The force close after an update
  is a user report.
- **Measured:** an update can change package content while `1.info` keeps its version (lab notebook,
  2026-10-10); `Watchdog` holds no per-file checksum, size or version, only package names, timestamps
  and the package-hash merge history.

The pristine delta is what lets the patcher put pristine bytes back where a diff needs them.

## Out of Scope

- **Layers patched before this ships, on the Android patcher.** `releaseSession` already deleted their
  snapshot bulk, so there is nothing to build a delta from; the first repatch after this ships still
  needs the data cleared.

## Open questions

- Does the game accept a re-patched override layer without clearing, with no repair on launch? The
  ordinary re-run over an already-patched layer suggests it does, but no switch has been run on a phone.
