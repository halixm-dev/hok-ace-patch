# Home screen brief

Status: confirmed 2026-10-17; amended 2026-10-19 for Remove translation, Free up space and the result states

The home screen both patchers share, in every state. Builds on `DESIGN.md`, `PRODUCT.md` and the
[spec](spec.md); used by the Android tickets 08 to 13 and the Windows tickets 14 to 16.

## 1. Job and audience

A player who doesn't read Chinese, patching their own phone. They follow instructions and rarely
read logs. They arrive with the game installed and its download finished, wanting it in English or
Indonesian. Mode: **Operate**. Clarity and getting the task done outrank visual expression.

## 2. Outcome and proof

- The task: choose a language, press **Start**, then watch progress with the game kept closed.
- Success: a final message stating what was applied and what stayed Chinese, followed by the Scan to
  login instruction.
- The facts the screen must state: the translation is partial, the game stays closed during work,
  login is Scan to login, and the app is unofficial. No invented numbers; counts come from the run.

## 3. Selected direction

- Look: `DESIGN.md`. The design is already established, so no new concept work.
- The idea: one guided column, where the eye goes ① → ② → progress.
- Focus point: the **② Start card**, which holds the screen's only primary button. Once work starts,
  the card becomes the progress view in place: the button turns into the bar and the
  "Step N of 7 · <step>" line, so the player's attention never has to move.
- Implementation:
  - The hero is compact: eyebrow, title, and one line covering the partial translation and Scan to
    login. No tall banner.
  - The log sits below ② at lower priority, in a fixed-height panel.
  - Technical tools go last.

## 4. Scope and boundaries

Production-ready home screen for both patchers, in every state below.

**Unchanged:**
- Consent checkboxes start unchecked.
- Android behaviour, action tags, callbacks and test tags.
- The 60 dp minimum button height on Android.
- The language lock while work runs.
- Raw technical logs.

**Anti-goals:**
- Looking like a Tencent product.
- A second primary button competing with Start. Remove translation and Free up space are secondary.
- A dashboard of status tiles.
- Hiding the partial-translation note.
- Warnings that alarm or blame.

## 5. States and ranges

| State | What ② Start shows | Notes |
|---|---|---|
| Idle, ready | Start button, "Ready when you are" line | Windows: device connected, folder with enough free space |
| Not ready | Start still visible, with the blocker as the next step | Windows: phone not connected, or folder short of space. Android: Shizuku missing or stopped; the button becomes Install / Start Shizuku |
| Running | Progress bar, "Step N of 7 · <step>", **Stop safely** (Android) | Language card locked. Log follows the latest line |
| Needs attention | Warning card directly under ② | Android recovery, storage shortfall (needed, free and to-clear GB), interrupted run |
| Success | *Translation added*: completion counts (text tables and images applied or skipped), then the Scan to login note | Button becomes **Run again** (Windows) or **Start another patch** (Android) |
| Removed | *Translation removed*: original game files restored, then the Scan to login note and how to get the official app | Same button as Success |
| Written, unconfirmed | *Translation written* (Android): recovery closed a run whose translation is on the phone but was not checked | **Start another patch**; nothing runs automatically |
| Space freed | *Space freed* (Android): space freed and free now, and what was kept | Button returns to **Start** |
| Notice | One `text-muted` line under ②'s instruction, such as "Access was not allowed. Tap Start to try again." | Not a card; replaced by the next notice |
| Failed | Error card with the cause, **Copy error details** (Android) and the next step | Button becomes **Try again**. Log and "Save log for help" stay reachable |

**Ranges:**
- Indonesian strings run about 30 % longer than English.
- The Android storage message is four lines.
- Completion counts go up to 5 digits.
- The log runs to thousands of lines (fixed height, scrolls inside).

## 6. Interaction and layout

- **Order, top to bottom:**
  1. Hero.
  2. ① Language: the title, the language note (no clear needed while a pristine delta is held,
     otherwise clear first), the two choices, then **Remove translation** as a secondary button,
     shown only while a pristine delta is held.
  3. ② Start. On Windows it opens with a short "Before you start" checklist, then device status
     and the working folder, above the button.
  4. Warning or error card, when one exists. On Android the warning card is "Game won't open?"
     with its recovery options folded.
  5. Log.
  6. The version, then one row of text buttons: Technical tools, Check for updates and, on Android,
     Free up space. They are not full-width buttons.
- **Windows:** one centred column, at most 720 px wide, in a resizable window. The page scrolls
  when it's shorter than the content. The log is open but secondary, since it's the only progress
  detail the Windows patcher has.
- **Android:** full width less 16 px gutters. The page scrolls, and the log scrolls inside its own
  panel.
- **Feedback:**
  - Each state change rewrites ② in place.
  - Switching language while idle redraws the whole interface at once.
  - A disabled control uses the disabled colours rather than just looking dimmed.

## 7. Constraints and open decisions

**Fixed:**
- Light only.
- Barlow fonts.
- Every string from `resources/ui/strings.json`.
- No Tencent artwork.
- CustomTkinter on Windows, with solid cards.
- Android 11 and later.
- It must survive large system fonts on Android and 150 % Windows scaling.

**Not this change:** the Windows patcher has no Stop button. Adding one is behaviour and out of
scope, so its ② card stays without one.
