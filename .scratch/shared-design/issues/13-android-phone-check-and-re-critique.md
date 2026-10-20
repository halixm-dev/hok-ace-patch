# 13: Android phone check and re-critique

**What to build:** Prove the restyled Android home screen on a phone. See the [spec](../spec.md), "Testing Decisions".

- Follow `docs/runbooks/device-cycle.md`. Capture each state in the brief at the default and the largest font size, in English and Indonesian, and look at each screenshot. No game operation is needed beyond ticket 11's patch.
- Re-run `/impeccable critique` on the Android home screen and compare it with the 26/40 run of 2026-10-19.
- Record the evidence in `docs/lab-notebook.md`.

**Blocked by:** 09, 10, 11, 12

**Status:** done (2026-10-20)

- [x] Every state of the brief captured at both font sizes and in both languages
- [x] No clipped or overlapping text
- [x] Critique re-run and its score recorded
- [x] Lab notebook entry

## Comments

2026-10-20: Done on the Redmi Note 9 Pro (Android 15). The debug build went over the release in place (patcher key and lineage, versionCode 58), so the pristine delta stayed and no uninstall was needed; a copy sits outside the repo. New `HomeStatesCaptureTest` draws all 13 states of the home screen brief as full pages in both languages and fails on ellipsized, word-broken, vertically clipped or overflowing text. It ran at font scale 1.0 and 2.0, and all 52 captures were looked at. It found the footer breaking labels inside words at 2.0. Fix: `FooterRow` stacks the three text buttons when a label's longest word will not fit, plus 8 dp above the log panel. After the fix the capture test, `InterfaceProbeTest` and `GuidedHomeProbeTest` pass at both sizes. `/impeccable critique` scored 29/40, up from 26/40. Its remaining P2s (the ② eyebrow on result states, the duplicate Save log in the failed state, and the recovery toggle label) are not part of this ticket. Evidence: `docs/lab-notebook.md`, 2026-10-20.

Ticket 11's Indonesian patch is still open. The spec makes it the one game operation this check may need, and none of these captures needed it, so 13 closes without it. The brief and DESIGN.md now allow the stacked footer.
