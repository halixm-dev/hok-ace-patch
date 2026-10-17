# Language switch without clearing the game's data

Status: needs-triage

## Problem

A phone that is already translated cannot change language, or take a newer translation of the same
data version, without clearing the game's data. Clearing costs a ~2.7 GB re-download and a login.

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

After each install, the patcher keeps a **restore delta**: for every package file it wrote, the
pristine bytes of the ranges it overwrote and the pristine length. On a later run of the same data
version, the patcher checks that every file the delta names still holds the bytes the last install
wrote, rebuilds the pristine files from them and the delta in its own local copy of the layer, and
builds the new language from that. The phone receives one write per staged file, exactly as a normal
install does. Nothing pristine is ever pushed back to the phone.

A run whose check fails (the game updated or repaired a patched file, or the data version changed)
does not use the delta, and the user is told to clear the game's data, as today.

## Implementation Decisions

- **One shared module, `tools/restore_delta.py`.** `make(pristine_dir, staged_dir) -> Delta`,
  `write(delta, path)` / `read(path)`, and `restore(layer_dir, delta, out_dir)`. The Windows front end
  calls it from `patcher_core`; Android calls it through `android_bridge`. No Kotlin reimplementation:
  the delta is made and applied by the engine both front ends already ship.
- **Delta format.** One file per install, schema-versioned JSON header plus a zlib body. Per package
  file: its path relative to `packages/`, the pristine length and SHA-256, the staged length and
  SHA-256, and the overwritten ranges as `(offset, length)` with their pristine bytes. A file the patch
  created (none today) records pristine length 0 and restores as deleted.
- **Range detection.** Compare in 4 KiB blocks, then 64-byte sub-blocks inside a changed block, and
  coalesce changed runs closer than 256 bytes (the measured parameters). Always read both files whole
  from disk, never from in-memory staging state, so the delta describes the bytes actually written.
- **The delta always points at pristine.** When a run starts from a restored layer, its new delta is
  made against the rebuilt pristine files, not against the previous install. One delta per data
  version is ever kept; there is no chain.
- **Self-verifying.** `restore` refuses unless each named file's length and SHA-256 equal the delta's
  staged values, and verifies each rebuilt file against the pristine SHA-256 before the build reads it.
  A mismatch is a `PatchError` that says to clear the game's data.
- **When a delta is made.** Only after the install is verified complete: Windows after
  `push_translation`, Android after `GameFileTransaction.finishApply`. It is written atomically and
  replaces the previous one only once it is durable. An interrupted install keeps the old delta, which
  still describes the layer: rollback restores those bytes.
- **When a run may make the first delta.** Only from a layer this patcher has no record of patching:
  no delta exists for this data version, and the run's text pass translated records in every text
  table it staged. A layer patched by an older patcher version (no delta) does not qualify; the user
  clears once, and every later switch is free.
- **Where it lives.** Windows: `<working folder>/restore/<data version>/delta.bin`. Android:
  `filesDir/restore/<data version>/delta.bin`, outside `sessions/`, so `releaseSession` never reclaims
  it. Deltas for any other data version are deleted at the start of a run.
- **Build input on Android.** `snapshot/` must keep the phone's actual bytes, because rollback writes
  them back. The rebuilt pristine files go into a separate build-input copy of only the files the delta
  names (~0.9 GB), with the rest of the layer read from `snapshot/`. `build_storage.estimate` reserves
  that copy.
- **Windows build input.** `pull_game_data` already extracts its own copy into
  `sessions/<stamp>/game`; `restore` rewrites the named files there in place. `device-backup.tar` keeps
  the phone's actual bytes.
- **Front ends.** Both pickers and `README.md` stop saying to clear before switching when a delta for
  the phone's data version exists; the run log names which path it took (`restored N files from the
  restore delta` or the reason it could not).
- **Vocabulary.** Add **Restore delta** to `GLOSSARY.md`: the pristine bytes an install overwrote, kept
  so a later run of the same data version can rebuild the pristine layer.

## Testing

- Offline round trip, no device: for English and Indonesian builds over the pristine 1.6.0.1 snapshot,
  `restore` over the staged layer reproduces every pristine SHA-256. A `tools/research/` check.
- Offline switch: English stage, then `restore` + Indonesian build from the result; its staged files
  are byte-identical to an Indonesian build straight from the pristine snapshot. The same for
  Indonesian then English, and for English then English (a rerun).
- Refusals: a named file one byte different, one truncated, one missing, and a delta from another data
  version each refuse with the clear-data message and write nothing.
- Device cycle ([device-cycle](../../docs/runbooks/device-cycle.md)): English install, then switch to
  Indonesian without clearing; the lobby reads MULAI GAME with Indonesian text, no in-game repair runs,
  and the login survives. Then switch back to English.

## Out of Scope

- **Game updates.** An in-game update that touches a patched file invalidates the delta; a run after
  an update still needs the data cleared (ADR 0002 is unchanged). Rebuilding pristine for the files an
  update did not touch is possible later but not specified here.
- **Layers patched before this ships.** They have no delta; the first switch after this ships still
  needs the data cleared.
- **Uninstalling the translation** (restoring pristine onto the phone with no new patch). The delta
  makes it possible, but it is a separate feature with its own write path.

## Open questions

- Is "translated records in every staged text table" a reliable pristine signal, or does the game carry
  its own file hashes (a package `.info`, the global index) the patcher could compare instead?
- Does the game accept a re-patched override layer without clearing, with no repair on launch? The
  ordinary re-run over an already-patched layer suggests it does, but no switch has been run on a phone.
