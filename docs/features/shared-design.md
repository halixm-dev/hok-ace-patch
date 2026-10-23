---
feature: shared-design
status: built; Android phone-checked, Windows checked from source
updated: 2026-10-23
branch: master
---

# One design for both patchers

## Report

Both patchers now follow one design, taken from the rendered wxq.qq.com page and recorded in
`DESIGN.md`. They read the same colours, corners, spacing and type from `resources/ui/theme.json`, the
same fonts from `resources/fonts/` (Barlow and Barlow Condensed, OFL), and every user-facing string from
`resources/ui/strings.json` in English and Indonesian. The home screen is one column on both: hero,
① Language, ② Start, the warning or error card, the log, then the footer. ② rewrites itself in place
for each state, and while work runs it shows a bar and "Step N of M · <step>". The interface follows the
language choice on both patchers.

The 98 Indonesian strings marked `"draft": true` in `strings.json` have not been reviewed by a native
speaker. Ticket 01 was closed with that review still owed. The drafts include the Windows patcher's
interface and its 20 error messages (`error_*`, `clear_game_data`, `use_other_patcher`).

| what landed | where |
|---|---|
| the design and its tokens | `DESIGN.md` (front matter), `resources/ui/theme.json` |
| the shared strings and their check | `resources/ui/strings.json`, `tools/research/check_ui_strings.py` |
| fonts and licence | `resources/fonts/`, listed in `android/native/THIRD_PARTY.md` |
| Android: theme, fonts and strings from the shared files | Gradle `stageUiResources`, `UiText` |
| Android: ① Language, ② states, cards, footer, recovery grouping | `GuidedHome`, `PanelDialog`, `FooterRow` |
| Android: progress reports its step (six steps) | `WorkerStep`, `PatchWorkerService.show`, `UiText.step` |
| Windows: theme, fonts, single column, ② states, ① Language | `app/hok_patcher.py` |
| Windows: interface language, dialogs, device hints, errors from the strings file | `patcher_core.ui_text`, `set_interface_language`, `PatchError(*keys, **values)` |
| Windows: no builder DLLs in the exe | `app/build_exe.py` (2.6 MB smaller) |

### Verification

| check | result |
|---|---|
| `tools/research/check_ui_strings.py` | 275 strings, each in en and id; both patchers resolve to them. It also fails a Windows `PatchError` raised with text instead of keys |
| `InterfaceProbeTest`, `GuidedHomeProbeTest`, `HomeStatesCaptureTest` on the Redmi Note 9 Pro (Android 15) | pass at font scale 1.0 and 2.0 in both languages; all 52 captures of the brief's 13 states looked at (`docs/lab-notebook.md`, 2026-10-20) |
| `testDebugUnitTest`, `assembleDebug`, `assembleDebugAndroidTest` | pass |
| one Indonesian patch on the phone (patcher 1.6.1.12) | ② read "Langkah N dari 6 · <step>" through all six steps; 389 text tables and 398 images applied, 1 text table skipped; the game reached its login screen in Indonesian |
| `/impeccable critique` of the Android home screen | 29/40, up from 26/40; its three P2s were then fixed |
| Windows states and dialogs, driven from source and screenshotted | every state and both dialog kinds at 100 % in English, the main states at 150 % (CTk scaling) in Indonesian |
| `build.bat`, then `--selftest` on the 20261017 dump | `ok: true` in English and Indonesian; the exe opens its main window |
| `tools/research/check_windows_repatch.py` | 14 tests pass |

The Windows patcher has not been run against a phone with this design, and its 150 % check used
CustomTkinter's scaling rather than Windows display settings.

### Journey

- **Tickets 03, 04 and 07** (restyle each patcher whole, Android progress) were split into vertical
  slices 08 to 16 and closed as `wontfix`.
- **The Android step list** became six steps, not the Windows seven: verification is not a step of
  its own, because each install already checks the installed app. Recovery, first setup and Free up
  space keep their own wording and show no count.
- **The footer at font scale 2.0** broke labels inside words ("Technic|al tools"). `FooterRow` now
  stacks the three text buttons when a label's longest word does not fit; the brief and `DESIGN.md`
  were amended to allow it.
- **The critique's P2s**: ②'s eyebrow now follows the state (READY TO PLAY, IN PROGRESS, DONE, NEEDS
  ATTENTION), the recovery toggle reads *Hide* while open, and each screen offers one *Save log for help*.
- **The Indonesian patch** found that step 3 also covers keeping the previous run's session delta when
  recovery finished that run. It stays one step. The activity log now carries steps 1 and 2 across the
  confirmation.
- **Windows tickets 14 to 16** landed together, since 15 replaced the layout 14 would have restyled.
  The hero and dialog panels are drawn with PIL, because CustomTkinter has no transparency. Review
  changes:
  - *Retry install?* is a plain question; only reinstalling and closing mid-run use a danger dialog.
  - The added counts use a Windows-only `applied_counts`, because `completed_counts` opens with
    "Normal game app verified" and only the Android patcher verifies the app.
  - The log stays raw English: `str(PatchError)` is English, and the error card shows `shown()`.

## [S1] Problem

A player who doesn't read Chinese patches their phone with the Windows patcher or the Android patcher,
and the two looked and read like two different products:

- The Windows patcher was dark, with a left sidebar of seven step rows, and English only.
- The Android patcher was light lavender, with rounded glass cards, and switched between English and
  Indonesian.

Neither followed the game's website closely. The first `DESIGN.md` was extracted from wxq.qq.com's
CSS alone, so it recorded the browser's default link blue as the brand colour.

Controls added since 2026-10-17 (Remove translation, the language note, Free up space, the result
states) were placed differently on each patcher. Many of their strings were missing from the shared
strings file. A critique of the Android home screen (26/40) found more problems:

- While work ran, a spinner and a free-text line gave no sense of progress, and Indonesian fell back
  to one generic sentence.
- Notices and the error box appeared below the log.
- About twenty full-width secondary buttons competed with Start.
- The hero's eyebrow leaned official.

## [S2] Design

**Look.** The site as rendered (sampled 2026-10-17) wins over either patcher as built. The design is
light only:

- **Page and cards:** a lavender page gradient with frosted white glass cards, and a solid fallback on
  Windows.
- **Ink and buttons:** indigo ink and a deep-indigo primary button.
- **Panels:** the hero and dialogs are deep-indigo panels with the site's ice-blue confirm button.
- **Warnings and errors:** warnings use the site's amber; errors use a red marked patcher-only.
- **Shape:** 8 px corners and no drop shadows.
- **Type:** four steps (title, heading, body and label), in Barlow with Barlow Condensed ExtraBold for
  the title. The hero is drawn locally, with no Tencent artwork.

Each patcher keeps its toolkit: CustomTkinter on Windows, its own views on Android.

**Screen.** One column, in this order:

1. **Hero.** Eyebrow `COMMUNITY PATCHER  /  HOK ACE`, the title, and one line on the partial
   translation and Scan to login.
2. **① Language.** The title, then the two-variant language note: no clear is needed while a
   pristine delta is kept, otherwise clear the game's data first. Then the two choices and the
   secondary Remove translation.
   - Remove translation shows only while a delta is kept, locks with the choices while work runs, and
     confirms with a plain dialog.
3. **② Start.** It holds the only primary button and rewrites itself in place for each state:
   - idle and not ready;
   - running, with a bar and "Step N of M · <step>";
   - the results, each with its run's counts: *Translation added*, *Translation removed*,
     *Translation written* and *Space freed*;
   - failed.
   - On Windows, the card also holds the checklist, the device status and the working folder above
     Start.
4. **Warning or error card,** directly under ②. On Android the warning card is "Game won't open?"
   with its recovery options folded. The error card holds the cause and *Save log for help*, plus
   *Copy error details* on Android.
5. **Log.**
6. **Footer.** The version, then a row of text buttons.

**Progress.** The Android worker state carries a stable step key and a total beside its free-text
line, and older states without one still show their line.

**Shared files.** `theme.json` is generated from `DESIGN.md`'s front matter. `strings.json` holds
every user-facing string under a stable key. Placeholders are written `{name}`, and unreviewed
Indonesian is marked `draft`. Gradle copies the files into the APK, and the Windows exe bundles them.

Action tags, protocol keys, durable records and raw technical logs stay untranslated. The Windows exe
stopped bundling Tencent's builder DLLs.

## [S3] Out of Scope

- Sharing the device workflow between the patchers.
- Recovery and Free up space on the Windows patcher.
- On Windows, a Stop button, a consent checkbox on the Remove translation dialog, and the footer's
  Technical tools and Check for updates (it has neither feature).
- The phone's status before Start on Windows: only `wait_for_device` polls adb, so a missing phone
  is not an idle blocker there.
- A dark theme, the site's cut-corner button, a toolkit change on Windows, and any Tencent artwork,
  logo or font.
- Changing any action tag, callback, consent default or the 60 dp minimum button height on Android.
