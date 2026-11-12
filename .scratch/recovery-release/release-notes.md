## What changed

- Recover damaged texture packages, including the reported `15_0.db` missing B-tree slot, through a targeted Re-download.
- Check mixed game data and missing texture slots together, so detected problems share one deletion and download round.
- Use **Review Re-download → Delete and re-download → Open game → Downloads finished**. Deletion happens directly from the reviewed file list; returning to the patcher waits for your answer.
- Refuse deletion if the reviewed plan or game data changed.

## Good to know

- This release contains only the recovery fix. Unfinished automatic-continuation changes are excluded.
- The affected Redmi was unavailable. Recovery is checked offline and in an emulator; the original corruption cause and that phone's full re-download cycle remain unverified.
- Translation is partial. Finish every game download before continuing, and keep using **Scan to login**.

## Install

Install **hok-ace-patch.apk** over your existing patcher to keep its saved recovery files. ARM64, Android 11 or newer; Shizuku, Wireless debugging or root access is required.

`SHA256SUMS` verifies the APK download. The codec source companion is for source and license notices; it is not needed for installation.
