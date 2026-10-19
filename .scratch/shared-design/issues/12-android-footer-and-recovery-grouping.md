# 12: Android footer and recovery grouping

**What to build:** The secondary actions stop competing with Start. See the [spec](../spec.md), "Screen".

- The footer is the version, then one row of text buttons: Technical tools, Check for updates and Free up space.
- Inside the "Game won't open?" card, the recovery options stay folded and lead with *Restore interrupted patch*. The other tools sit in a quieter "More recovery tools" group.
- Free up space's dialog is a plain panel, and its "also remove saved game apps" checkbox starts unchecked.
- Behaviour is unchanged: the `show-technical`, `check-app-update`, `free-space`, `free-space-recovery` and recovery tags, their callbacks, and the 60 dp minimum height of every touch target.

**Blocked by:** 08, 06

**Status:** ready-for-agent

- [ ] Footer as one text-button row
- [ ] Recovery options grouped, Restore first
- [ ] Tags and callbacks unchanged (probe)
- [ ] Touch targets still at least 60 dp
