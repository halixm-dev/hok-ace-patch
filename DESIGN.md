---
name: HOK ACE Language Patcher
description: A status-first workspace with light periwinkle cards and indigo actions.
colors:
  page-top: "#3F459A"
  page-mid: "#737CD9"
  page-bottom: "#C4CCF7"
  card: "#EEF1FF"
  card-solid: "#EEF1FF"
  card-edge: "#B8C0EE"
  card-sweep-lilac: "#E6DCFA"
  card-sweep-blue: "#CFD6FA"
  surface: "#FFFFFF"
  surface-subtle: "#E2E6FD"
  ink: "#161B4A"
  text-muted: "#434978"
  outline: "#6E74A3"
  panel-top: "#343B8E"
  panel-bottom: "#262B73"
  on-panel: "#FFFFFF"
  on-panel-muted: "#EEF1FF"
  accent-gold: "#F2CF66"
  confirm-right: "#BFC6FF"
  success: "#1B6B45"
  success-surface: "#D6F5E3"
  warning: "#7A5400"
  warning-surface: "#FFEDCC"
  error: "#BA1A1A"
  error-surface: "#FFDAD6"
  disabled-fill: "#E2E6FD"
  disabled-text: "#62678E"
typography:
  title:
    fontFamily: Barlow Condensed
    fontWeight: 800
    fontSize: 32px
  heading:
    fontFamily: Ace Heading
    fontWeight: 700
    fontSize: 20px
  body:
    fontFamily: Commissioner
    fontWeight: 400
    fontSize: 14px
  label:
    fontFamily: Commissioner
    fontWeight: 600
    fontSize: 12px
    letterSpacing: 0.025em
  button:
    fontFamily: Commissioner
    fontWeight: 600
    fontSize: 14px
  log:
    fontFamily: Fragment Mono
    fontWeight: 400
    fontSize: 12px
rounded:
  card: "20px"
  button: "12px"
  field: "12px"
spacing:
  xxs: "4px"
  xs: "8px"
  sm: "12px"
  md: "16px"
  lg: "20px"
  xl: "24px"
  section: "32px"
components:
  button-primary:
    backgroundColor: "{colors.panel-bottom}"
    textColor: "{colors.on-panel}"
    typography: "{typography.button}"
    rounded: "{rounded.button}"
  button-primary-hover:
    backgroundColor: "{colors.panel-top}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.button}"
    rounded: "{rounded.button}"
  button-secondary-hover:
    backgroundColor: "{colors.surface-subtle}"
  button-text:
    backgroundColor: transparent
    textColor: "{colors.ink}"
    typography: "{typography.button}"
    height: "48px"
  button-danger:
    backgroundColor: "{colors.error}"
    textColor: "{colors.on-panel}"
    typography: "{typography.button}"
    rounded: "{rounded.button}"
  button-disabled:
    backgroundColor: "{colors.disabled-fill}"
    textColor: "{colors.disabled-text}"
  card:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "{spacing.lg}"
  folder-path:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.field}"
    padding: "{spacing.xs}"
  status:
    backgroundColor: "{colors.surface-subtle}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    padding: "4px 12px"
  status-verified:
    backgroundColor: "{colors.success-surface}"
    textColor: "{colors.success}"
  status-attention:
    backgroundColor: "{colors.warning-surface}"
    textColor: "{colors.warning}"
  choice:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.button}"
    rounded: "{rounded.field}"
  choice-selected:
    backgroundColor: "{colors.surface-subtle}"
  target-selected:
    backgroundColor: "{colors.panel-bottom}"
    textColor: "{colors.on-panel}"
    typography: "{typography.button}"
    rounded: "{rounded.button}"
    height: "36px"
---
# Design System: HOK ACE Language Patcher

## Overview

**Creative North Star: "Status first"**

The Android patcher and both Windows targets share the Stitch workspace. The masthead identifies
the community patcher and its installed version. On Android, the supplied white mark sits
behind the gradient HONOR OF KINGS ACE wordmark. Light cards give the current state, its next
action, and setup clear places in the workspace.

Keep the interface calm while the patcher works and specific when the player needs to act. Show
the worker's current step and use the run's own counts for results.

**Key Characteristics:**

- Indigo shell with light periwinkle cards and white inset surfaces.
- Current status before setup, with the next action within reach.
- Gold metadata in the masthead and explicit labels for verified results and attention.

## Colors

| Role | Use |
|---|---|
| Primary | The indigo shell uses the page gradient on Android and solid `page-top` on Windows. Use deep indigo and white text for the primary action. |
| Secondary | Gold is the masthead's community, edition, and version metadata. |
| Neutral | Windows cards use a fine edge. Android status and setup use a borderless white-to-periwinkle sweep. White surfaces hold paths, activity, and Android result counts. Use `ink` for content and `text-muted` for supporting copy. |
| Status | Pair the neutral, amber, green, and red treatments with labels. Use neutral periwinkle for progress, amber for attention, green for verified results and live USB connection, and red for errors and destructive confirmation. |
| Disabled | Use the disabled fill and text for locked choices and unavailable actions. |

**The Verified Success Rule.** Show a verified result in green. The status label tells the
player what the patcher verified.

## Typography

| Role | Family and size |
|---|---|
| Masthead | Android wordmark rendered at a 32 sp reference size from the supplied title font. Windows uses Barlow Condensed ExtraBold (32). |
| Section heading and Android count | Ace Heading Bold (20) |
| Instructions and details | Commissioner Regular (14) |
| Labels and status | Commissioner SemiBold (12). Android adds 0.025 em tracking. |
| Controls | Commissioner SemiBold (14) |
| Activity | Fragment Mono Regular (12) |

Ace Heading is a static Hubot Sans instance with a separate font name. Barlow Condensed is the
bundled display face for Windows. The Android wordmark ships as a PNG drawn from the supplied
`honor-of-kings-ace-title.otf`. The four UI font families ship with their licenses. The
numbers are scaled text units on Android and logical pixels on Windows. Follow Android font
settings and Windows display scaling.

## Layout

Use 16 dp or logical px outer gutters and a 20 dp or logical px inset on cards. Separate the
status, setup, and activity surfaces with the spacing scale.

- **Android.** Keep status and setup in the scrolling body. Pin the current action above the
  navigation bar. Place the closed-game and download instructions before Start patching, keep
  language and connection method in one setup card, and open the connection guide on demand.
  Use two columns for language choices and result tiles at 360 dp or wider with a font scale
  of 1.15 or less. Use one column at smaller widths or larger font sizes. Running
  work hides setup and shows progress and activity. The update icon sits beside the masthead
  version and has a 48 dp touch target, tooltip, and spoken label.
- **Windows.** Put the target switch next to the masthead. From 740 logical px of workspace
  width, place status and its actions beside setup in a 3-to-2 grid. At smaller widths, stack
  status and setup. Activity sits below the workspace at both widths. Wrap full folder paths
  and keep a single Save log for help action visible.

## Elevation & Depth

Use tonal layering for depth. The shell frames the periwinkle cards, and white surfaces sit
inside the cards. The Android setup and status cards sweep from white through lilac and blue.
Tonal fill and the radio indicator distinguish selected Android choices.

## Shapes

Use 20 dp or logical px corners for cards and 12 dp or logical px corners for buttons and
fields. Status labels are compact and rounded. Let controls grow with wrapped text on Android.

## Components

### Buttons and choices

- The primary action uses the indigo gradient on Android home and a solid indigo on Windows.
  Android home pins the raised primary button above the centered Technical tools and Free up
  space links. The page background continues behind the footer.
  Secondary buttons use white with a fine outline. Android also uses text buttons for help and
  other secondary actions. Home actions have at least a 48 dp touch target, or 56 dp for the
  primary action.
- Android choices use radio controls. A selected row uses a periwinkle fill and a checked radio indicator.
  Put a short prerequisite below each connection method. Windows target and language choices
  use the filled button for selection. On Windows, Tab
  reaches enabled buttons and scrolls them into view. Enter or Space activates the focused
  button. Focus changes the border, and hover changes the fill.

### Task status

- Show the next step and put recovery or error details close to it. Saved work takes priority
  in the next action. During work, show progress and the current step, with Stop safely
  where available.
- Let the heading carry the status when a chip would repeat it. The Android access heading
  uses amber. The Windows USB ready heading carries the ready state.
- On Windows, the Android USB target pairs live connection status with the working folder and
  language. Put Save log for help beside the recovery action while saved work waits, in an
  error card when one is visible, and beside Activity otherwise.
  PC setup shows game and working folders, available space, and language. PC status
  presents Install, Check, and Remove translation for the measured state. Running work locks
  target, language, and setup.
- On Android, a verified result that leaves the game ready to play leads with Open game.
  Show applied and skipped totals in white count tiles. Use the amber callout for Scan to login
  where applicable.

### Dialogs

Use a light card with clear actions. Consent checkboxes open unchecked. Reserve red for the
destructive action. Remove translation asks for one confirmation.
On Windows, Tab reaches Cancel before the destructive action, and Escape closes the dialog.

## Do's and Don'ts

- **Do** keep shared English and Indonesian text in `resources/ui/strings.json`. The selected
  translation sets the interface language. Technical logs keep their original wording.
- **Do** describe translation coverage in the results. Label counts as applied or skipped.
- **Do** use the 208 dp white mark from the Android frames in `new-ui.figcraft` as a
  15% opacity watermark in the upper-right background. The first card can cover its lower edge.

`resources/ui/theme.json` supplies the runtime tokens. Gradle generates the Android resources
from it, and the Windows patcher reads it directly.
