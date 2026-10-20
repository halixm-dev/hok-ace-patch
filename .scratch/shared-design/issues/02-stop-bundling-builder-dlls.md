# 02: Stop bundling the builder DLLs

**What to build:** the Windows exe no longer ships Tencent's package builder (see [spec](../spec.md), "Builder DLLs").

- Remove the `qtsvfs` `--add-data` from `app/build_exe.py`. `patcher_core` already runs without a builder: `find_builder_dir` returns nothing and the append covers prime-only content.
- `AGENTS.md`: the `resources/qtsvfs/` Boundaries line becomes "kept in the repo for `--builder` runs from source, not shipped"; the Architecture row says the same. Update `README.md`'s layout row.
- Check: `build.bat`, then `"dist\HOK ACE Language Patcher.exe" --selftest <game-dir> <out-dir>` succeeds, and `build_device_patch.py --apk <apk>` with no `--builder` logs `no QtsVFS builder given` (the selftest passes no APK, so it never reaches that line); the exe is smaller by the DLLs' compressed size (about 2.6 MB of their 7.7 MB).

**Blocked by:** nothing

**Status:** done

- [x] DLLs out of the exe
- [x] `AGENTS.md` and `README.md` updated
- [x] `--selftest` passes on the rebuilt exe

## Comments

2026-10-20: done. The exe went from 64,289,091 to 61,673,469 bytes, 2.6 MB smaller. The 7.7 MB is the DLLs' raw
size, and PyInstaller compresses them. The rebuilt archive holds no `QtsVFS.dll` or `QtskDB.dll`.
`--selftest` on the 20261016 pristine dump: `ok: true`. The selftest passes no APK, so it never
reaches the builder branch and cannot log `no QtsVFS builder given`. That line was checked from source
instead: `build_device_patch.py --apk installed.apk` with no `--builder` logs it, exits 0, and adds
293 + 1 + 71 + 1 assets from the APK.
