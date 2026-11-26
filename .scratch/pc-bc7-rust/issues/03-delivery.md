# Package and verify the Windows encoder

Status: ready-for-human (everything but the PC cycle on the installed game is done; see the spec's Handoff)

Depends on ticket 02.

1. Wire the release extension into [build.bat](../../../build.bat), [the freezer](../../../app/build_exe.py) and [Windows CI](../../../.github/workflows/windows.yml). Use a pinned build toolchain and locked crate dependencies. Build for the same architecture as the bundled Python 3.12 interpreter. End users should need only the executable. Document any changed contributor build commands in the README.
2. Extend the frozen smoke check with a deterministic block that reaches mode 7. Assert that the native function ran and that the output matches the Python reference fixture. Also exercise a source run without the extension. Run the ordinary offline checks:

   ```bat
   .venv\Scripts\python.exe tools\research\check_graphics.py
   build.bat
   "dist\HOK ACE Language Patcher.exe" --smoketest "<work>\smoke"
   ```

3. Compare reference and native cold catalogs for English and Indonesian using the same game copy and separate work folders. Check affected payload bytes, patched and skipped atlas lists, deterministic re-encoding, and warm cache reuse. Run the frozen `--pc-selftest <game-copy> <out-dir>` on a disposable copy. Follow the [PC cycle runbook](../../../docs/runbooks/pc-cycle.md) for install, switch and restore verification.
4. Record per-language cold and warm medians, mode 7 wall time, native call count, parity failures and frozen executable size change in the lab notebook. Report which checks ran on a real game copy. Document the shipped path in the PC edition feature record. If parity fails or cold builds show no repeatable improvement, retain the Python release path and record the limiting step.
