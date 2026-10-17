# 02: The pristine delta module

**What to build:** `tools/pristine_delta.py`, shared by both patchers: `make(pristine_dir, staged_dir) -> Delta`, `write(delta, path)`, `read(path)` and `rebuild(layer_dir, delta, out_dir)`, as the [spec](../spec.md)'s Implementation Decisions describe.

- Format: schema-versioned JSON header plus a zlib body. Per package file: path relative to `packages/`, pristine length and SHA-256, staged length and SHA-256, overwritten ranges `(offset, length)` with their pristine bytes. A file the patch created records pristine length 0.
- Range detection: 4 KiB blocks, then 64-byte sub-blocks, changed runs closer than 256 bytes coalesced. Both files read from disk, never from staging state.
- `rebuild` takes a file only at its entry's staged length and SHA-256 and verifies each rebuilt file against the pristine SHA-256; it reports per file which were rebuilt, which already hold pristine, and which match neither, so callers can apply the update rules.
- A `tools/research/` check: for English and Indonesian builds over the pristine 1.6.0.1 snapshot, `rebuild` reproduces every pristine SHA-256; English → `rebuild` → Indonesian stages byte-identical to Indonesian from pristine, and the same for Indonesian → English and English → English. One-byte-changed, truncated and missing files are reported, never rebuilt.

**Blocked by:** nothing

**Status:** ready-for-agent

- [ ] `tools/pristine_delta.py` with module docstring, type hints, `PatchError` for user-facing failures
- [ ] Offline round-trip and switch check passes for both languages
- [ ] Measured delta size recorded against the lab notebook's 5.12 / 3.87 MB

## Notes

The measurement scripts behind the lab notebook entry (2026-10-17, "Reverse delta…") were throwaway; the parameters there are the ones to use.
