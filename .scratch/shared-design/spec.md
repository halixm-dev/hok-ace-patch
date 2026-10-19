# One design for both patchers

Status: ready-for-agent

Revised 2026-10-19 against Android patcher 1.6.1.10, including that day's `/impeccable critique` of
the Android home screen (26/40, from source). The home screen in every state is set by the
[home screen brief](home-screen-brief.md).

## Problem Statement

A player who doesn't read Chinese patches their phone with the Windows patcher or the Android patcher.
The two look and read like two different products:

- The **Windows patcher** is dark, with a left sidebar of seven step rows. Its interface is English
  only.
- The **Android patcher** is light lavender: one column of rounded 18 dp glass cards. Its interface
  switches between English and Indonesian.

Neither follows the game's website closely. The first `DESIGN.md` was extracted from wxq.qq.com's CSS
alone. The site draws its look with images, so that extraction recorded the browser's default link
blue as the brand colour.

Since 2026-10-17 both patchers have gained controls, and each placed them its own way:

- **Remove translation.** Android shows it inside ① Language, only while it keeps a pristine delta,
  with a plain confirmation and a consent checkbox. Windows always shows it under Start, as "Remove
  Translation", with a danger confirmation.
- **Language note.** Both patchers say whether switching needs a clear, in different words. The
  shared strings file has only the older "clear first" line.
- **Free up space** (Android only). It sits in the footer and in the recovery options.
- **Result states.** Android has four: translation added, removed, written (unconfirmed), and space
  freed. Windows has two.
- **Strings missing from the shared file.** 18 Android strings from these controls, and four texts
  the Android patcher builds in code, are not in the shared strings file. Moving either patcher onto
  that file today would drop them.

The critique found more problems on the Android patcher:

- While work runs, the player sees a spinner and a free-text line, with no sense of how far along it
  is. In Indonesian, any progress line not in the translation table becomes one generic sentence.
- Notices and the error box appear below the log, away from the Start card the player is watching.
- Below Start, about twenty full-width secondary buttons have equal weight.
- The hero's eyebrow reads `HONOR OF KINGS / ACE`, which leans official.

## Solution

Both patchers follow one design, taken from the rendered wxq.qq.com page and recorded in `DESIGN.md`.
They read the same colours, corners, fonts and strings from shared files, and show the same home
screen:

- **Hero.** A compact hero that says the patcher is unofficial and the translation partial.
- **① Language.** The two choices, the language note, and a secondary Remove translation button.
- **② Start.** The card holds the only primary button. It turns into progress in place, as a bar and
  "Step N of M · <step>", and then into the result.
- **Under ②.** A warning or error card appears directly under it when one exists.
- **Below.** The log, then a quiet footer.

The interface follows the chosen language on both patchers. Behaviour does not change: the Android
patcher keeps its recovery and automatic continuation, and the Windows patcher keeps its seven
device steps.

## User Stories

1. As a player, I want both patchers to look like one product, so that I trust the one I didn't download first.
2. As a player, I want the patcher not to look like a Tencent product, so that I know it is an unofficial community tool.
3. As a player, I want the hero to tell me the translation is partial and that I log in with Scan to login, so that neither surprises me later.
4. As a Windows patcher user, I want the interface in Indonesian when I choose the Indonesian translation, so that I can follow every step.
5. As an Android patcher user, I want switching the language to redraw the whole screen at once, so that I never see a mix of languages.
6. As a player, I want the same words for the same thing on both patchers, so that help written for one works for the other.
7. As a player, I want one obvious primary button, so that I know what to press next.
8. As a player, I want the Start card to become the progress view in place, so that my eyes never have to move while work runs.
9. As a player, I want a progress bar and "Step N of M · <step>", so that I know how far along the run is and that it is still moving.
10. As an Indonesian player, I want the progress step in Indonesian, so that I am not left with a generic "processing" line at the moment that matters.
11. As a player, I want the language choice locked while work runs, so that I can't change a run half-way.
12. As a player whose phone this patcher translated, I want a line telling me that switching language needs no clear, so that I don't wipe my game data for nothing.
13. As a player whose phone another patcher or an older version translated, I want a line telling me to clear the game's data first, so that the switch works.
14. As a player, I want Remove translation only when this patcher can actually remove it, so that I don't press a button that can only refuse.
15. As a player, I want Remove translation to look secondary to Start, so that I don't remove the translation by mistake.
16. As a player, I want Remove translation's confirmation to say that no game data is deleted, and to look calm rather than alarming, so that I understand the consequence.
17. As a player, I want the removal result to say how many original game files were restored, and that I still use Scan to login, so that I know what state the game is in.
18. As a player, I want the success result to list the text tables and images applied and skipped, so that I know what stayed Chinese.
19. As a player, I want counts called *applied*, never *covered*, so that the patcher doesn't overclaim.
20. As an Android patcher user, I want a "Translation written" result when recovery closed a run whose translation is on the phone, so that I know nothing is broken and nothing runs on its own.
21. As an Android patcher user, I want Free up space to show what it freed and what it kept, so that I know recovery still works.
22. As an Android patcher user, I want the option to remove the saved game apps to start unchecked and state the space the next patch will need, so that I choose with the cost in view.
23. As a player, I want a short notice (such as "Access was not allowed. Tap Start to try again.") inside the Start card, so that I see it where I am looking.
24. As a player whose run failed, I want an error card directly under Start with the cause and the next step, so that I can recover without reading the log.
25. As a player whose run failed, I want to copy the error details and save a log for help, so that someone can help me.
26. As an Android patcher user whose game won't open, I want a warning card with the recovery options folded, Restore interrupted patch first, so that I take the safest step first.
27. As a player, I want the footer (Technical tools, Check for updates, Free up space) to be quiet, so that it doesn't compete with Start.
28. As a support helper, I want the technical tools still reachable, so that I can guide a player through a manual step.
29. As a player using large system fonts, I want every card and button to stay readable without clipping, so that I can use the patcher at my font size.
30. As a Windows patcher user at 150 % display scaling, I want the single column to fit and scroll, so that nothing is cut off.
31. As a screen-reader user, I want headings marked as headings and disabled controls described as disabled, so that I can find my place.
32. As a player, I want disabled controls drawn in the disabled colours, not only dimmed, so that I can tell they are disabled.
33. As a Windows patcher user, I want my phone's status and the working folder's free space inside the Start card, so that I see blockers before pressing Start.
34. As a Windows patcher user, I want a smaller download, so that the exe that no longer needs Tencent's builder DLLs doesn't carry them.
35. As a maintainer, I want every user-facing string in one shared file with English and Indonesian, so that a wording fix lands in both patchers at once.
36. As a maintainer, I want an offline check that fails when a patcher uses a string the shared file lacks, so that a new control can't ship untranslated.
37. As a native Indonesian reviewer, I want draft translations marked, so that I know which strings to check.

## Implementation Decisions

**Look**
- The site as rendered (sampled 2026-10-17) wins over either patcher as built. The theme is light
  only; a dark theme comes later, to both patchers at once.
- **Colours.** A lavender page gradient and frosted white glass cards; the solid fallback is the
  glass composited over the page. Indigo ink, and a deep-indigo primary button. Hero and
  confirmation dialogs are deep-indigo panels with the site's ice-blue confirm button. Warnings use
  the site's amber; errors use a red marked patcher-only.
- **Shape and type.** 8 px corners on cards and buttons, no drop shadows, no cut-corner button.
  Barlow for body text, Barlow Condensed ExtraBold for the hero title, the system CJK font for the
  game's Chinese name. Four type steps: title, heading, body and label.
- **Toolkits stay.** The Windows patcher stays on CustomTkinter, with solid cards and the gradient
  only in a locally drawn hero image. The Android patcher draws the glass with its own views.
- **Hero.** Drawn locally, with eyebrow `COMMUNITY PATCHER  /  HOK ACE`, the app title, and one line
  on the partial translation and Scan to login. No Tencent artwork, logo or image.

**Screen**
- **One column:** hero, ① Language, ② Start, the warning or error card, the log, then the footer.
- **① Language** holds the title, the language note and the two choices. Below the choices sits
  Remove translation, a secondary outlined button.
  - Both patchers show Remove translation only while they keep a pristine delta (Windows: in its
    working folder). It locks with the language choice while work runs.
  - Its confirmation is a plain dialog, not a danger one, because nothing is deleted.
  - The Android consent checkbox stays; Windows adds none.
- **The language note** has two shared variants: no clear needed while a pristine delta is kept,
  otherwise clear the game's data first.
- **② Start** rewrites itself in place for each state: idle, not ready, running, the result states,
  and failed. The result states are added, removed, written-unconfirmed and space freed, and each
  shows the run's own counts as a short list.
  - Windows uses the same headings for the states it has.
  - The Windows ② card also holds a short checklist, device status and the working folder, above
    Start.
- **Notices** are one muted line inside ②. Anything that needs action is the warning card.
- **The error card**, under ②, holds the cause, Copy error details (Android) and Save log for help.
- **Recovery** (Android only). The "Game won't open?" warning card, with its options folded and
  Restore interrupted patch first. The other recovery tools sit in a quieter group.
- **The footer** is the version, then one row of text buttons: Technical tools, Check for updates
  and, on Android, Free up space. Free up space's "also remove saved game apps" checkbox starts
  unchecked, and its dialog is plain.

**Progress**
- The Android worker state gains a stable step key and a total beside its free-text line.
- ② shows a determinate bar and "Step N of M · <step>" from the shared strings. The free-text line
  moves to the log.
- Recovery, first setup and Free up space keep their own wording and show no count.
- Older states without a step still show their line.
- The Android step list is its own, not the Windows seven, and is confirmed in ticket 11.

**Shared files**
- **Theme file:** colours, radii and spacing, generated from `DESIGN.md`'s front matter.
- **Strings file:** every user-facing string of both patchers in English and Indonesian, under
  stable keys. Placeholders are written `{name}`, and Indonesian not yet reviewed by a native
  speaker is marked `draft`.
  - It also holds templates for texts the Android patcher builds in code today (space freed, the
    remove-saved-apps option, the removal confirmation, the removal result).
- **Fonts folder:** the Barlow fonts and their licence.
- Gradle copies all three into the APK, and the Windows exe bundles them.
- The Android `UiText` module and the Windows GUI read the strings file. Their in-code tables go.
  Action tags, protocol keys, durable records and raw technical logs stay untranslated.

**Packaging**
- The Windows exe stops bundling Tencent's builder DLLs. They stay in the repo for builder runs from
  source.

**Documents**
- `DESIGN.md` records the layout, components and states above.
- `PRODUCT.md` records that repatching after an in-game update ships in both patchers. It was
  checked offline, not yet on a real update.

## Testing Decisions

- A good test checks what the player sees or what a file promises, never how a view is built:
  the text under a tag, a state's heading, a string's presence in both languages.
- **Shared strings contract (offline).** A new research check, in the style of the existing offline
  checks, asserts:
  - every string the Android `UiText` module and the Windows GUI show resolves to a key in the
    strings file;
  - every key has English and Indonesian;
  - every placeholder appears in both languages.

  This is the single seam that keeps the patchers on one vocabulary. Prior art: the reference and
  staging-contract checks.
- **Android interface (instrumented).** Extend `InterfaceProbeTest`, which already launches the real
  activity, drives it by view tag, switches language and saves a screenshot. Add:
  - Remove translation is hidden with no pristine delta and shown with one;
  - the result headings render in both languages;
  - the progress line shows "Step N of M" when the worker state carries a step.

  `GuidedHomeProbeTest` stays as it is.
- **Worker progress.** The state record's step key and total are checked where the worker state is
  already checked, through the instrumented probe reading the saved state. There is no new seam
  inside the worker.
- **Windows patcher.** No test suite. Verify with `run.bat` in both languages at 100 % and 150 %
  scaling, then `build.bat` and `--selftest`. The selftest must log that no builder was given.
- **Visual check.** On a phone, per the device-cycle runbook: default and largest font size, both
  languages, with each state's screenshot looked at. No game operation is needed except ticket 11's
  one Indonesian patch.

## Out of Scope

- Sharing the device workflow between the patchers.
- Recovery and Free up space on the Windows patcher.
- A Stop button on Windows.
- A consent checkbox on the Windows Remove translation dialog.
- A dark theme.
- The site's cut-corner button.
- A toolkit change on Windows.
- Any Tencent artwork, logo or font.
- Changing any action tag, callback, consent default or the 60 dp minimum button height on Android.

## Further Notes

- 41 Indonesian strings from ticket 01 are still marked `draft`. The strings ticket 05 adds come from
  the shipped Android table and are not drafts.
- The critique snapshot is in `.impeccable/critique/`. Re-run `/impeccable critique` on the Android
  home screen in ticket 13 to compare.
- When the last ticket lands, promote this spec to `docs/features/shared-design.md`, following the
  issue-tracker conventions.

## Tickets

Tickets 03, 04 and 07 were split into the vertical slices 08 to 16 and closed as `wontfix`.

1. [Design docs and shared resources](issues/01-design-docs-and-shared-resources.md)
2. [Stop bundling the builder DLLs](issues/02-stop-bundling-builder-dlls.md)
5. [Shared strings for the newer controls](issues/05-shared-strings-for-newer-controls.md)
6. [Record the newer controls in the design docs](issues/06-record-newer-controls-in-design-docs.md)
8. [Android on the shared theme, fonts and strings](issues/08-android-on-the-shared-theme-fonts-and-strings.md), after 01 and 05
9. [Android ① Language card](issues/09-android-language-card.md), after 08 and 06
10. [Android ② states, notices and cards](issues/10-android-start-states-notices-and-cards.md), after 08 and 06
11. [Android progress reports its step](issues/11-android-progress-reports-its-step.md), after 10
12. [Android footer and recovery grouping](issues/12-android-footer-and-recovery-grouping.md), after 08 and 06
13. [Android phone check and re-critique](issues/13-android-phone-check-and-re-critique.md), after 09 to 12
14. [Windows on the shared theme, fonts and strings](issues/14-windows-on-the-shared-theme-fonts-and-strings.md), after 01 and 05
15. [Windows single column with progress in ②](issues/15-windows-single-column-with-progress.md), after 14 and 06
16. [Windows ① Language and result states](issues/16-windows-language-card-and-result-states.md), after 15 and 06
