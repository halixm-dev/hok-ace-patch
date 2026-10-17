# 02: Stop bundling the builder DLLs

**What to build:** the Windows exe no longer ships Tencent's package builder (see [spec](../spec.md), "Builder DLLs").

- Remove the `qtsvfs` `--add-data` from `app/build_exe.py`. `patcher_core` already runs without a builder: `find_builder_dir` returns nothing and the append covers prime-only content.
- `AGENTS.md`: the `resources/qtsvfs/` Boundaries line becomes "kept in the repo for `--builder` runs from source, not shipped"; the Architecture row says the same. Update `README.md`'s layout row.
- Check: `build.bat`, then `"dist\HOK ACE Language Patcher.exe" --selftest <game-dir> <out-dir>` logs `no QtsVFS builder given` and succeeds; the exe is about 7.7 MB smaller.

**Blocked by:** nothing

**Status:** ready-for-agent

- [ ] DLLs out of the exe
- [ ] `AGENTS.md` and `README.md` updated
- [ ] `--selftest` passes on the rebuilt exe
