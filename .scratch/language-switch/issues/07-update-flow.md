# 07: Repatch after an in-game update, in one Start Patch run

**What to build:** the [spec](../spec.md)'s Game updates flow in both patchers, adjusted to what 01 measured.

- Start when any holds on an already-patched phone: (i) a file the delta names changed since the install; (ii) `Watchdog/History.db` has merge events dated after the install; (iii) the user answers yes to "Did the game update, crash, or show Chinese text since the last patch?", asked only when (i) and (ii) are quiet.
- Run: access APK, write pristine back to every file still at its staged hash (06's transaction), normal APK; tell the user to open the game, let the update finish to the login screen and close it; wait for confirmation; access APK, pull, build, write, normal APK.
- A file the update replaced becomes its new pristine when the pristine signals hold for it; a file that fails them (half Chinese, half English) refuses with the clear-data message.
- The new delta is made against the post-update pristine layer.
- `README.md` "Updates and language changes" describes the flow; ADR 0002's Consequences already allow the write-back.

**Blocked by:** 01, 06

**Status:** ready-for-agent

- [ ] Signals (i)–(iii) as 01 found them to behave (dropped: no signal fires before an update runs; (ii)
      measured after it, (i) and (iii) not built; see Notes)
- [ ] Two-access-cycle run in both patchers, with the user's confirmation step (dropped, see Notes)
- [x] Replaced-file acceptance and the mixed-file refusal (2026-10-18, offline): per package, by the
      delta's asset record (`pristine_delta.accept_replaced`), then the text signal; both patchers.
      `tools/research/check_update_repatch.py` on the real 1.6.0.1 packages with faked updates.
- [x] Device cycle at a real update: update finishes, repatch succeeds, no clear, login kept (Android
      patcher, 2026-10-23: no clear, the login screen reached, and the user checked the game reads Indonesian;
      the repeat the same day kept the login after the repatch)
- [x] One Re-download for a stuck update: it also takes the mixed packages restore cannot
      (`plan_redownload`; `tools/research/check_update_redownload.py` on the captured phone states)

## Notes

2026-10-18: the acceptance side ships without the pristine write-back before the update. A run after
an update the game finished accepts each package the update changed cleanly and refuses the rest, as
before. Whether a real update leaves packages clean (repair restores every translated asset, or the
package is downloaded whole) or mixed is ticket 01's question; the faked updates only stand in for it.
The write-back and signals (i)–(iii) still wait on 01.

2026-10-23, after ticket 01's capture. The game starts its update the moment it opens, with no prompt,
and nothing on the phone changes before then (`NewVersionInfo.json` stays the same), so signals (i)–(iii)
can only fire after the update ran, and the pristine write-back before it has no moment to run. The spec
owner chose the after-update path: the Android patcher's Re-download (stuck package) and asset restore
(mixed packages) already recover without a clear, measured on the phone. What changed here:
`plan_redownload` takes the stuck packages and the mixed packages restore cannot take in one run, where
the phone needed two (`1`, then `10` and `21`). Checked offline against the real captures:
`after-update` plans `1`, `10`, `21`; `after-finish` plans `10`, `21`, as the phone did. On a phone the
same day (Round A repeated, update 1.6.0.1 → 1.7.0.2) one Re-download deleted `1`, `10` and `21`, and Start
then patched with no refusal (lab notebook, "One Re-download takes a stuck package and the mixed ones
together"). The Windows patcher still does not detect a stuck update;
the spec owner's choice leaves that side as it was (Re-download is Android-only).
Done.
