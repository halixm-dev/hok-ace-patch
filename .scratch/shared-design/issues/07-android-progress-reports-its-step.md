# 07: Android progress reports its step

**What to build:** the Android worker says which step it is on, so ② can show a determinate bar and "Step N of M · <step>" in English and Indonesian (see [spec](../spec.md), "Progress reports a step").

Today ② shows an indeterminate spinner and the worker's free-text `progress` line. `UiText.progress` translates only the lines in its table. Any other line becomes "Sedang memproses file game. Lihat rincian di log di bawah.", so an Indonesian player loses the status at the moment it matters.

- Decide the Android step list, which is not the Windows seven. Draft: check game, prepare files, unlock access, build translation, write translation, restore game app, verify. Record it in `GLOSSARY.md` if a new term appears.
- The worker state gains `step` (a stable key) and `steps` (the total) beside `progress`. Older states without them still show the free-text line.
- `strings.json` gains one key per step name (ticket 05's file). ② shows the bar and "Step N of M · <step>". The free-text line moves to the log.
- Recovery, first setup and Free up space keep their own wording and show no step count.
- Check: unit tests and `InterfaceProbeTest`; one patch on a phone in Indonesian, with a screenshot of each step (`docs/runbooks/device-cycle.md`).

**Blocked by:** 05

**Status:** wontfix (superseded by 11)

- [ ] Step list decided
- [ ] Worker reports `step` / `steps`
- [ ] Step names in `strings.json`
- [ ] Checked on a phone in Indonesian

## Comments

2026-10-19: split into vertical slices; superseded by ticket 11.
