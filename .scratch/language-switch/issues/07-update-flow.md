# 07: Repatch after an in-game update, in one Start Patch run

**What to build:** the [spec](../spec.md)'s Game updates flow in both patchers, adjusted to what 01 measured.

- Start when any holds on an already-patched phone: (i) a file the delta names changed since the install; (ii) `Watchdog/History.db` has merge events dated after the install; (iii) the user answers yes to "Did the game update, crash, or show Chinese text since the last patch?", asked only when (i) and (ii) are quiet.
- Run: access APK, write pristine back to every file still at its staged hash (06's transaction), normal APK; tell the user to open the game, let the update finish to the login screen and close it; wait for confirmation; access APK, pull, build, write, normal APK.
- A file the update replaced becomes its new pristine when the pristine signals hold for it; a file that fails them (half Chinese, half English) refuses with the clear-data message.
- The new delta is made against the post-update pristine layer.
- `README.md` "Updates and language changes" describes the flow; ADR 0002's Consequences already allow the write-back.

**Blocked by:** 01, 06

**Status:** ready-for-agent

- [ ] Signals (i)–(iii) as 01 found them to behave
- [ ] Two-access-cycle run in both patchers, with the user's confirmation step
- [x] Replaced-file acceptance and the mixed-file refusal (2026-10-18, offline): per package, by the
      delta's asset record (`pristine_delta.accept_replaced`), then the text signal; both patchers.
      `tools/research/check_update_repatch.py` on the real 1.6.0.1 packages with faked updates.
- [ ] Device cycle at a real update: update finishes, repatch succeeds, no clear, login kept

## Notes

2026-10-18: the acceptance side ships without the pristine write-back before the update. A run after
an update the game finished accepts each package the update changed cleanly and refuses the rest, as
before. Whether a real update leaves packages clean (repair restores every translated asset, or the
package is downloaded whole) or mixed is ticket 01's question; the faked updates only stand in for it.
The write-back and signals (i)–(iii) still wait on 01.
