# 09: Android ① Language card

**What to build:** ① Language shows its title, then the language note, then the two choices, then **Remove translation** as an outlined secondary button. See the [spec](../spec.md), "Screen", and the [home screen brief](../home-screen-brief.md).

- The note uses its two shared variants: no clear is needed while a pristine delta is kept; otherwise clear the game's data first.
- Remove translation shows only while a pristine delta is kept, and locks with the choices while work runs.
- Locked choices are drawn in the disabled colours, not only dimmed.
- Behaviour is unchanged: the `remove-translation` tag, its callback, and the confirmation with its consent checkbox. The dialog is drawn as a plain panel with the ice-blue confirm button.

**Blocked by:** 08, 06

**Status:** ready-for-human (run `InterfaceProbeTest` on a device)

- [x] Order: title, note, choices, Remove translation
- [x] Remove translation hidden without a pristine delta, shown with one (probe)
- [x] Disabled colours while work runs
- [ ] Probe passes in both languages

## Comments

2026-10-19: ① Language now reads title, note, choices, then Remove translation (`language-card` tag). Locked choices take `disabled-fill` and `disabled-text` from state lists, with no alpha change; Remove translation locks with them. The patch confirmation, in both its start and remove forms, is drawn by `PanelDialog`: the panel gradient, `on-panel` heading, `on-panel-muted` message, ice-blue confirm and a secondary Cancel; the consent checkbox and its gating are unchanged. The Free up space confirmation takes the same panel, since `DESIGN.md` now says both dialogs are plain; its checkbox still starts unchecked. `InterfaceProbeTest.languageCardOffersRemovalOnlyWithAPristineDelta` checks the order, the note variant and Remove translation's visibility with and without a delta in both languages, and the disabled colours; it moves a kept delta aside and restores it. `assembleDebug`, `assembleDebugAndroidTest` and `testDebugUnitTest` pass. Not run on a phone: the attached one holds the release patcher, which a debug build cannot replace without an uninstall.
