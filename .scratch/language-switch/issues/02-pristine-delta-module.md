# 02: The pristine delta module

**What to build:** `tools/pristine_delta.py`, shared by both patchers: `make(pristine_dir, staged_dir) -> Delta`, `write(delta, path)`, `read(path)` and `rebuild(layer_dir, delta, out_dir)`, as the [spec](../spec.md)'s Implementation Decisions describe.

- Format: schema-versioned JSON header plus a zlib body. Per package file: path relative to `packages/`, pristine length and SHA-256, staged length and SHA-256, overwritten ranges `(offset, length)` with their pristine bytes. A file the patch created records pristine length 0.
- Range detection: 4 KiB blocks, then 64-byte sub-blocks, changed runs closer than 256 bytes coalesced. Both files read from disk, never from staging state.
- `rebuild` takes a file only at its entry's staged length and SHA-256 and verifies each rebuilt file against the pristine SHA-256; it reports per file which were rebuilt, which already hold pristine, and which match neither, so callers can apply the update rules.
- A `tools/research/` check: for English and Indonesian builds over the pristine 1.6.0.1 snapshot, `rebuild` reproduces every pristine SHA-256; English → `rebuild` → Indonesian stages byte-identical to Indonesian from pristine, and the same for Indonesian → English and English → English. One-byte-changed, truncated and missing files are reported, never rebuilt.

**Blocked by:** nothing

**Status:** ready-for-agent

- [x] `tools/pristine_delta.py` with module docstring, type hints, `PatchError` for user-facing failures
- [x] Offline round-trip and switch check passes for both languages
- [x] Measured delta size recorded against the lab notebook's 5.12 / 3.87 MB

## Notes

The measurement scripts behind the lab notebook entry (2026-10-17, "Reverse delta…") were throwaway; the parameters there are the ones to use.

## Comments

2026-10-17, implemented. `tools/pristine_delta.py`; check `tools/research/check_pristine_delta.py`
(13 synthetic cases; `--game` for the real data). On the pristine 1.6.0.1 snapshot: English 11 files
rebuilt + 3 staged unchanged of 14, delta **5.12 MB** encoded (6.14 MB raw); Indonesian 11 + 3 of 14,
**3.87 MB** (4.67 MB raw), the lab notebook's figures exactly. English → Indonesian, Indonesian → English
and English → English each stage byte-identical files to a build from pristine. Refusals: one byte
changed and truncated report `changed`, a deleted file `missing`, and none is touched. Beyond the
ticket: `rebuild(..., fallback=)` (the Windows patcher's pending delta), `files_at`, the staged-hash
record and `text_not_pristine` (the second pristine signal, from the summary: the text pass's planned
tables equal `counts["tables"]`: 94 of 94 on pristine in both languages, 2 of 389 over an English
layer). `DeltaError` is the module's failure; each front end turns it into its own `PatchError`.
