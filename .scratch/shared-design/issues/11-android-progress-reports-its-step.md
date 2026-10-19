# 11: Android progress reports its step

**What to build:** While work runs, ② shows a determinate bar and "Step N of M · <step>" in the player's language. See the [spec](../spec.md), "Progress".

Today ② shows a spinner and the worker's free-text line. `UiText` translates only the lines in its table; any other line becomes one generic Indonesian sentence.

- Confirm the Android step list, which is not the Windows seven. Draft: check game, prepare files, unlock access, build translation, write translation, restore game app, verify.
- The worker state gains a stable step key and a total beside its free-text line. The free-text line moves to the log.
- Step names go in the shared strings file.
- Recovery, first setup and Free up space keep their own wording and show no count. Older states without a step still show their line.

Supersedes ticket 07.

**Blocked by:** 10

**Status:** needs-triage (confirm the step list)

- [ ] Step list confirmed
- [ ] Worker reports the step key and total
- [ ] Bar and step line in ② (probe, with a saved state that carries a step)
- [ ] One Indonesian patch on a phone, with each step's screenshot looked at
