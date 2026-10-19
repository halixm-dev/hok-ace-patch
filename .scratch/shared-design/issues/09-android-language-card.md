# 09: Android ① Language card

**What to build:** ① Language shows its title, then the language note, then the two choices, then **Remove translation** as an outlined secondary button. See the [spec](../spec.md), "Screen", and the [home screen brief](../home-screen-brief.md).

- The note uses its two shared variants: no clear is needed while a pristine delta is kept; otherwise clear the game's data first.
- Remove translation shows only while a pristine delta is kept, and locks with the choices while work runs.
- Locked choices are drawn in the disabled colours, not only dimmed.
- Behaviour is unchanged: the `remove-translation` tag, its callback, and the confirmation with its consent checkbox. The dialog is drawn as a plain panel with the ice-blue confirm button.

**Blocked by:** 08, 06

**Status:** ready-for-agent

- [ ] Order: title, note, choices, Remove translation
- [ ] Remove translation hidden without a pristine delta, shown with one (probe)
- [ ] Disabled colours while work runs
- [ ] Probe passes in both languages
