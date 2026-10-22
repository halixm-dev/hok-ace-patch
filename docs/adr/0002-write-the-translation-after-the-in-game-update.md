# Write the translation only after the in-game update

Tencent's updater patches packages with binary diffs against their original contents, so a package we changed before the update finishes breaks the diff, and the game's repair cannot converge on a package it does not recognise (every diff fails CRC, `errorCode:361`). A run therefore writes the translation only once the in-game update has completed, onto a complete override layer; game data caught mid-update is also the measured cause of one startup crash. Evidence: [prime-rebuild.md, Out of Scope](../features/prime-rebuild.md#s3-out-of-scope), [prime-only-append.md, Problem](../features/prime-only-append.md#s1-problem), the journey-log entries *Rebuilding package `21` and putting it on the phone* and *The crash after the first device push* ([prime-rebuild.md, Report](../features/prime-rebuild.md#report)), and [lab notebook §2 Cause A (2026-09-30)](../lab-notebook.md#cause-a--an-incomplete-game-data-download-2026-09-30).

## Consequences

- **One write before an update is allowed: pristine bytes.** The repatch-after-update flow
  (`.scratch/language-switch/spec.md`) writes a patched file's pristine bytes back, rebuilt from its
  pristine delta, so the update's diffs find the content they expect. It writes no translation; the
  translation still goes on only after the update has finished.
- **An update already stuck on a translation.** Measured 2026-10-22: the updater refuses the whole update
  and lists the translated assets in `Watchdog/BrokenList.db`. Deleting the listed translated packages and
  clearing `Watchdog` lets the game download them whole and finish; the Android patcher offers this as
  Re-download damaged files ([update-stuck-redownload](../features/update-stuck-redownload.md)). It writes
  no translation either.
- **The evidence grade.** `errorCode:361` and the "binary diff" wording above come from the upstream PC
  patcher's README and were never measured here. The mechanism found since points the same way: the
  updater checks each asset against the CRC its package stores, and our writes leave those values
  pristine while changing the bytes ([lab notebook 2026-10-17](../lab-notebook.md#2026-10-17--what-the-games-updater-records-and-what-it-checks)).
