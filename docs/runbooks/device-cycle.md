# Device cycle

Run this before any device-gated change goes on a phone: an allowlist candidate, a texture change on a
reviewed edit, a change to the normal APK, or anything whose effect on a screen is only known by watching
it. A device cycle tests **one** change and ends in a verdict, recorded before the next cycle starts. The
measurements behind these steps are in [`docs/lab-notebook.md`](../lab-notebook.md) (§2, §11 and
2026-10-02). A config-bin cycle (`--cycle-asset`) adds its own prerequisites and verdict rules:
[`docs/features/extra-text-cycles.md`](../features/extra-text-cycles.md), "The device test loop for a cycle".

## Steps

1. **Let the game finish its update.** Open the game and let it reach the login screen on its own; after a
   game update that means clearing the data (`pm clear com.tencent.tmgp.osgame`), downloading it again, and
   only then patching. The patcher has no completeness check of its own, so confirm it:
   `Cache/Update/NewVersionInfo.json` reads `needDownloadSize == 0`, and the device data set is not well
   under ~2.8 GB. Patching an incomplete set crashes startup.
2. **Build offline against a dump of the phone's own version.** Compare
   `<dump>/WXQ_Data/Package/builtin/1/1.info` with the phone's `files/QtsVFSCache/packages/1/1.info`; they
   must name the same version. A staged package is a revision of one layer, so a dump from an older version
   reverts every asset the game changed since, the load stops at 0% and the game repairs the translation
   away. Then build with Python 3.12:

   ```bat
   .venv\Scripts\python.exe tools\build_device_patch.py --runtime resources\runtime --game <dump> ^
       --catalog resources\catalog --work <work> --output <out> --apk <apk>
   ```

   Read the staged asset back before pushing it.
3. **Check the normal APK's launcher name.** The rename lives only in the cached `installed.apk`. If
   `set_label(apk_manifest(cache), APP_NAME) != apk_manifest(cache)` is `True`, run the patcher once
   (`run.bat`) or apply the same rewrite by hand; otherwise step 7 puts the Chinese name back on the
   launcher.
4. **Back up `packages` and `Watchdog`** so the cycle can be rolled back. This needs the access APK, because
   `run-as` works only while it is installed:

   ```bat
   adb install -r "dist\HOK ACE Patcher Data\access.apk"
   adb exec-out run-as com.tencent.tmgp.osgame tar -cf - -C files/QtsVFSCache packages Watchdog > backup.tar
   ```

5. **Push the override layer.** Per staged package directory: `adb push <out>\<id>\*.db
   /data/local/tmp/hokace/<id>/`, `chmod -R 755`, then
   `run-as com.tencent.tmgp.osgame sh -c 'cp /data/local/tmp/hokace/<id>/* files/QtsVFSCache/packages/<id>/'`.
   Then `run-as ... rm -rf files/QtsVFSCache/Watchdog/*` and `rm -rf /data/local/tmp/hokace`. This is
   `patcher_core.push_translation`'s sequence (`app/patcher_core.py`).
6. **Pull anything else you need now.** The game cannot run under the access APK, so anything read with
   `run-as` (`QtsVFS.log`, `BrokenList.db`, a package) is read before the next step or after reinstalling
   the access APK.
7. **Reinstall the normal APK**: `adb install -r "dist\HOK ACE Patcher Data\installed.apk"`, and confirm the
   launcher reads `Honor of Kings: ACE`. The access APK must never stay installed: the game dies in Unity
   startup under it, which looks exactly like a broken patch.
8. **Launch and read the logs.** `adb logcat` for QtsVFS errors, and
   `/storage/emulated/0/Android/data/com.tencent.tmgp.osgame/files/bqLog/ccs_log/normal1.log` for the
   game's own repair (`errorCode:361`). Screenshot the login screen. If the game dies, follow
   [`read-a-crash.md`](read-a-crash.md) before blaming the change.
9. **Log in and walk the screens.** Use *Scan to login* (a re-signed APK cannot do direct WeChat/QQ login),
   then walk every screen the change could reach: the loading tips, the Chessplayer page, the lobby, the
   Card menu, the arena artwork, and the screen the change targets. A staged file that reads back correctly
   is not evidence about a screen.
10. **Record the verdict.** Pass or fail, the symptom with the screen named, and the date, written beside
    the hash it concerns in the code (for example `extra_text.CANDIDATE_ASSETS` or `SAFE_ASSETS`), and the
    raw evidence as a dated entry in the lab notebook. To roll back, push `backup.tar` back with the access
    APK and reinstall the normal APK.

## Done when

The user has seen the changed screen after logging in, the launcher reads `Honor of Kings: ACE`, the
access APK is no longer installed, and the verdict is written beside the hash in the code and dated in
the lab notebook.
