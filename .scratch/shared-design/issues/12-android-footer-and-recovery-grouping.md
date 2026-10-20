# 12: Android footer and recovery grouping

**What to build:** The secondary actions stop competing with Start. See the [spec](../spec.md), "Screen".

- The footer is the version, then one row of text buttons: Technical tools, Check for updates and Free up space.
- Inside the "Game won't open?" card, the recovery options stay folded and lead with *Restore interrupted patch*. The other tools sit in a quieter "More recovery tools" group.
- Free up space's dialog is a plain panel, and its "also remove saved game apps" checkbox starts unchecked.
- Behaviour is unchanged: the `show-technical`, `check-app-update`, `free-space`, `free-space-recovery` and recovery tags, their callbacks, and the 60 dp minimum height of every touch target.

**Blocked by:** 08, 06

**Status:** ready-for-human (run `InterfaceProbeTest` on a device, and look at the footer at the largest font size in both languages)

- [x] Footer as one text-button row
- [x] Recovery options grouped, Restore first
- [ ] Tags and callbacks unchanged (probe written, not run)
- [ ] Touch targets still at least 60 dp (probe written, not run)

## Comments

2026-10-20: The footer (`footer`) is the version (`patcher-version`), then one row (`footer-actions`) of three text buttons, Technical tools, Check for updates and Free up space, sharing the width equally. A long label wraps instead of leaving the row, and the buttons line up by their tops, not by baseline. Technical tools still opens its panel, now below the footer. In the "Game won't open?" card the options (`recovery-options`) stay folded and lead with Restore interrupted patch, still a secondary button. The other tools sit under a muted *More recovery tools* label (`more-recovery-tools`, new string `more_recovery_tools`) as text buttons. `button()` takes `plain` for a text button: no fill or edge, the ripple kept inside the corners, the disabled fill kept, and still 60 dp tall. The Free up space dialog already met the ticket (`PanelDialog.style`, checkbox unchecked), so it is unchanged. DESIGN.md gains a Text button row and the recovery group.

Tests: `InterfaceProbeTest.footerIsOneTextButtonRowAndRecoveryLeadsWithRestore` checks the version and the three buttons side by side, Technical tools toggling its panel, recovery folded then leading with Restore and the rest in the group, each tag's callback key, and every target at least 60 dp tall after layout. `testDebugUnitTest`, `assembleDebug`, `assembleDebugAndroidTest` and `check_ui_strings.py` pass. The probes were not run: the attached phone holds the release patcher 1.6.1.10, which a debug build cannot replace without an uninstall.
