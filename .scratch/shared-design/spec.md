# One design for both patchers

Status: ready-for-agent

## Problem

The Windows patcher and the Android patcher look and read like two different products. The Windows
patcher is dark, with a left sidebar of seven step rows, and its interface is English only. The
Android patcher is light lavender, one column, rounded 18 dp glass cards, and switches its interface
between English and Indonesian. Neither follows the game's website closely: `DESIGN.md` was extracted
from wxq.qq.com's CSS alone, and the site draws its look with images, so the extraction recorded the
browser's default link blue (`#0000EE`) as the brand colour and "0 px corners, no gradients".

## Solution

Both patchers follow one design taken from the rendered wxq.qq.com page, recorded in `DESIGN.md`.
They share the same colours, corners, fonts, screen structure and wording, and read them from shared
files. Behaviour does not change: the Android patcher keeps its recovery and automatic continuation,
the Windows patcher its seven device steps.

## Implementation Decisions

- **Reference.** The site as rendered, sampled from screenshots (2026-10-17), wins over the Android
  patcher as built. Both patchers move toward it.
- **Light only.** No dark theme yet; a dark theme comes later, to both patchers at once.
- **Colour roles.** Page: lavender gradient `#DCDCF1` → `#B5BAE5`. Cards: frosted white glass,
  about 85 % opaque with a thin white edge; the solid fallback `#F1F0FA` is the glass composited over
  the page. Text: indigo `#343876`. Primary button: deep-indigo fill `#5A5496` → `#343876`, white
  text. Hero and confirmation dialogs: deep-indigo panels with the site's ice-blue confirm button.
  Warning: the site's amber tag. Error: a red that `DESIGN.md` marks as patcher-only.
- **Corners.** 8 px on cards and buttons. The site's cut-corner button shape is left out.
- **Fonts.** Barlow (SIL OFL) for body text, Barlow Condensed ExtraBold for the hero title, the
  system CJK font for the game's Chinese name. The site's HYQiHei is commercial and is not shipped.
- **Toolkits stay.** The Windows patcher stays on CustomTkinter, which has no transparency: its cards
  use the solid fallback and the gradient appears only in the hero image. The Android patcher draws
  the glass.
- **One column, same cards.** Hero, ① Language, ② Start, logs, technical tools. The Windows Start
  card also holds device status and the working folder, above the Start button.
- **Progress.** A bar and one line, "Step N of 7 · <step>", inside the Start card. The Windows
  seven-row step list goes.
- **Interface language.** The Windows patcher switches its interface to Indonesian with the language
  choice, as the Android patcher does. Technical logs stay raw.
- **Shared files.** `resources/ui/theme.json` (colours, radii, spacing), `resources/ui/strings.json`
  (every user-facing string, English and Indonesian) and `resources/fonts/` (the Barlow TTFs). Gradle
  copies them into the APK; the Windows exe bundles them. `UiText` reads `strings.json` instead of its
  Kotlin table.
- **Hero artwork.** Drawn locally: the indigo gradient, the "COMMUNITY PATCHER / HOK ACE" eyebrow and the app
  title. No artwork, logo or image from the site or the game, which belong to Tencent.
- **Builder DLLs.** The Windows exe stops bundling `resources/qtsvfs/`; it stays in the repo for
  `build_device_patch.py --builder` runs from source. `REBUILD_PACKAGES` is empty and the append pass
  never loads the DLL.

## Out of Scope

Sharing the device workflow between the patchers, recovery on the Windows patcher, a dark theme,
the site's cut-corner button, a toolkit change on Windows, and any Tencent artwork.

## Tickets

1. [Design docs and shared resources](issues/01-design-docs-and-shared-resources.md)
2. [Stop bundling the builder DLLs](issues/02-stop-bundling-builder-dlls.md)
3. [Restyle the Windows patcher](issues/03-restyle-windows-patcher.md), after 01
4. [Restyle the Android patcher](issues/04-restyle-android-patcher.md), after 01
