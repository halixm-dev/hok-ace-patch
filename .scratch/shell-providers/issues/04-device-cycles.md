# 04: Device cycles for both new providers

**What to build:** evidence, not code. Prove each new provider on real phones before the early-testing release, following [device-cycle](../../../docs/runbooks/device-cycle.md). Record every result in `docs/lab-notebook.md`. See the [spec](../spec.md), *Testing*.

- Wireless: pairing by notification reply on at least two OEMs; a full patch; a run with the screen off; wireless debugging switched off mid-run (expect worker-loss recovery).
- Root on KernelSU (the test phone): whether files written as uid 0 need an explicit `chown` and `restorecon` before the game reads them; a full patch, a repatch and a restore. WeChat/QQ direct login on a phone first patched through root stays open: it needs a phone whose game was never re-signed, and the test phone's already is.
- Cross-provider: Shizuku then root, and root then Shizuku, on one phone, sharing one pristine delta.
- Then Magisk and APatch, each marked *tested* in the guide only after it passes.

**Blocked by:** 02, 03

**Status:** ready-for-human

- [ ] Wireless debugging cycles recorded
- [ ] Root on KernelSU cycles recorded
- [ ] Direct login under root (needs a never re-signed phone)
- [ ] Cross-provider cycle recorded
- [ ] Removing Shizuku: decide in its own ticket once each new provider has passed on two phones
