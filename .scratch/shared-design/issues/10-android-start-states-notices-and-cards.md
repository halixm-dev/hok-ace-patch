# 10: Android ② states, notices and cards

**What to build:** ② Start rewrites itself in place for every state the [brief](../home-screen-brief.md) lists, and anything that needs the player sits directly under it. See the [spec](../spec.md), "Screen".

- Result states: *Translation added*, *Translation removed*, *Translation written* and *Space freed*. Each shows the run's own counts as a short list, then the Scan to login note where the game app changed.
- Notices become one muted line inside ②, replacing the loose notice view under the log.
- The error card (cause, Copy error details, Save log for help) and the "Game won't open?" warning card move directly under ②, above the log. They use the error and warning colours.
- Behaviour is unchanged: the `copy-error`, `show-recovery` and recovery option tags, and their callbacks.

**Blocked by:** 08, 06

**Status:** ready-for-agent

- [ ] Four result states with count lists
- [ ] Notice line inside ②
- [ ] Error and warning cards under ②, above the log
- [ ] Probe checks the result headings in both languages
