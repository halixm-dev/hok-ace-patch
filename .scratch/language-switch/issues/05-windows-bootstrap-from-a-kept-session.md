# 05: Windows patcher builds a first delta from a kept session

**What to build:** when the Windows patcher holds no delta, it tries once to build one from a session it kept (`prune_old_sessions` keeps the last two), so a phone patched before this ships repatches without a clear.

- Candidate: a session whose `device-backup.tar` passes the pristine signals (no file at a recorded staged hash; the text pass finds Chinese in every staged text table), and whose `staged/` files equal the phone's current files by SHA-256.
- `make` the delta from that backup's package files against that `staged/`; then the run proceeds as 03.
- No candidate: the clear-data refusal, as 03.
- The Android patcher does not do this: `releaseSession` already deleted its snapshot bulk.

**Blocked by:** 03

**Status:** ready-for-agent

- [x] Bootstrap from a qualifying kept session, tried once per run with no delta
- [x] Offline check: a session over pristine bootstraps; a session over a patched layer does not

## Comments

2026-10-17, implemented as `Patcher.bootstrap_delta`. The backup's signals: none of its staged files at
a recorded staged hash, and `text_not_pristine` of that session's own `device_patch_summary.json`. The
check is `tools/research/check_windows_repatch.py` (bootstraps from a pristine session; refuses one
over a translated layer).
