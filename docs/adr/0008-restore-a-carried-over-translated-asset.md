# Restore a carried-over translated asset from its kept pristine chunks

Status: proposed. Built in the Android patcher and checked offline only; no device has run it, and the cycle that decides it (the next real game update over a restored package) can run only when Tencent ships one.

After a game update rewrites a translated package but keeps some assets this patcher modified (a mixed package), the Android patcher writes each such asset's pristine stored chunks and record fields back into a copy of the updated package, and takes the copy as the new pristine, instead of asking the user to re-download the package. It restores only an asset whose record still carries the pristine check token and whose chunk count is unchanged, through the in-place stager's own relocation (`Shard.relocate`, no key added), and verifies every restored asset by read-back against its pristine SHA-256 and stored chunks. Assets the install appended, any staged file still in the package, and anything that fails a check fall back to Re-download. This makes the patcher write bytes into a package the game last wrote, on the strength of a check value it cannot compute; the restored asset is pristine byte for byte, but whether the updater's next diff accepts it is unmeasured. It is neither the append pass (it adds no record) nor a rebuild (nothing is re-laid out), so ADR 0003 does not apply. Evidence: the 2026-10-22 r815437 update (lab notebook) and the design, sizes and device cycles in the asset restore spec (commit `a2526fa`, not merged); the built behaviour in [asset-restore](../features/asset-restore.md).

## Consequences

- The pristine delta keeps each modified asset's pristine stored chunks and index record: about 64 MB more for an English install of 1.7.0.1 (5.3 MB to 69.1 MB), stored uncompressed after the zlib body.
- A mixed package with an appended survivor (packages `10` and `21` on 2026-10-22) still needs Re-download: `qts_relocate` cannot remove a record.
- The Windows patcher refuses a restorable package like any other until it gains the same step.
- If a build over restored packages fails the text signal, every restored or replaced package goes to Re-download (`restore-refused.json` beside the delta) rather than being restored or accepted again.
