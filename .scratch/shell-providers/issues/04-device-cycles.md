# 04: Device cycles for both new providers

**What to build:** evidence, not code. Prove each new provider on real phones before the early-testing release, following [device-cycle](../../../docs/runbooks/device-cycle.md). Record every result in `docs/lab-notebook.md`. See the [spec](../spec.md), *Testing*.

- Wireless: pairing by notification reply on at least two OEMs; a full patch; a run with the screen off; wireless debugging switched off mid-run (expect worker-loss recovery).
- Root on KernelSU (the test phone): whether files written as uid 0 need an explicit `chown` and `restorecon` before the game reads them; a full patch, a repatch and a restore. WeChat/QQ direct login on a phone first patched through root stays open: it needs a phone whose game was never re-signed, and the test phone's already is.
- Cross-provider: Shizuku then root, and root then Shizuku, on one phone, sharing one pristine delta.
- Then Magisk and APatch, each marked *tested* in the guide only after it passes.

**Blocked by:** 02, 03

**Status:** ready-for-human

- [ ] Wireless debugging cycles recorded
- [x] Root on KernelSU cycles recorded
- [ ] Direct login under root (needs a never re-signed phone)
- [x] Cross-provider cycle recorded
- [ ] Removing Shizuku: decide in its own ticket once each new provider has passed on two phones

## Device findings

**2026-10-24, `fd071d1`, Redmi Note 9 Pro (`ebad528e`, Android 15, PixelAge, KernelSU): the cycles this phone can run, all pass.** Evidence in `docs/lab-notebook.md` (2026-10-24, ticket 04 on `ebad528e`) and `D:\hokace-work\redmi-ebad528e\t04\`. Each delta was compared by its header (per-file pristine and staged SHA-256 and lengths, body hashes), and each installed layer by the SHA-256 of its 14 package files against the delta's staged hashes.

- **Shizuku → Root.** A Shizuku patch (server started from adb, uid 2000) over the delta that the Wireless run left: `complete`, 11 files rebuilt from the delta, 14-file delta kept. Then a Root patch over that: `complete` (391 text tables, 398 images applied, 1 table skipped), 11 rebuilt from the Shizuku delta, no APK installed. The Root delta is identical to the Shizuku delta except for its `made` time. The 14 installed files match its staged hashes, all 1322 entries under `files/` are `u0_a246` with `app_data_file:s0:c246,c256,c512,c768`, and the game started to the English login with QTS scan `errorCode=0` and no QtsVFS errors.
- **Root → Shizuku.** A Shizuku patch over the Root delta: `complete`, 11 rebuilt from it, normal APK restored and verified. The delta is again identical except for `made`, the installed files match it, labels unchanged, and the game started English (`errorCode=0`).
- **Root loss after Shizuku, and the `fd071d1` fixes on the phone.** A Root patch killed with `pkill -9` after `15/15_0.db`: ③ *Root access stopped…*, error *Worker disconnected; recovery: Worker disconnected*. The recovery options showed *Restore interrupted patch* and *Free up space* only, with no *Reinstall saved game app*, although the retained normal APK (`recovery/63bec2…`) was still there (`c1-root-loss-recovery-options.png`). *Restore interrupted patch* → `recovered`; the files match the delta again, 1328 entries keep the owner and label, and the game started English. The Root result reads *Patch complete. The game app was not replaced.*
- **Wireless debugging with the screen off.** Patch started, then the phone set to unplugged (`dumpsys battery unplug`) and the screen turned off. Deep Doze reached `IDLE` within 3 minutes and stayed there for 22 of 26 polls. The run went on regardless: `complete` 13 minutes after the screen went off, 11 rebuilt from the delta, 14-file delta (identical except for `made`), normal APK restored (installed `base.apk` SHA-256 `63bec2…`). The installed files match the delta's staged hashes. The connection log now reads `Wireless debugging, Xiaomi …` with no `port -1`, and the port appears on its own line.
- **Not checked:** the game start after the screen-off run, because the phone came back to its secure lock screen and its code was not entered. Its 14 package files are byte-identical to the layer that started English in the Root → Shizuku run.
- **Observation:** after a Shizuku run, a `dev.halixm.hokacepatcher:device` process stays alive as `shell` with parent 1. That is Shizuku's user service, not a root worker. No uid-0 worker was left after any Root run.
- **Still open for this ticket:** pairing on a second phone maker; Magisk and APatch; direct WeChat/QQ login under root on a phone whose game was never re-signed.
