---
version: 1
name: HOK ACE Language Patcher
description: |
  The one design both patchers follow, taken from the game's website (wxq.qq.com):
  a light lavender page, frosted white cards, deep-indigo panels and heavy
  condensed titles. Light only.
source:
  url: "https://wxq.qq.com"
  sampledAt: 2026-10-17
  method: colours sampled from screenshots of the rendered page; the site draws its look with images, so its CSS alone misses it
colors:
  page-top: "#DCDCF1"
  page-bottom: "#B5BAE5"
  card: "rgba(255, 255, 255, 0.85)"
  card-solid: "#F1F0FA"
  card-edge: "rgba(255, 255, 255, 0.9)"
  ink: "#343876"
  text-muted: "#55597F"
  panel-top: "#5A5496"
  panel-bottom: "#343876"
  on-panel: "#FFFFFF"
  on-panel-muted: "#DCDCF1"
  confirm-left: "#EAEEF7"
  confirm-right: "#ADBEEC"
  warning: "#D2AA60"
  warning-surface: "#FBF1DD"
  error: "#C8414B"
  error-surface: "#FBE4E6"
  disabled-fill: "#E2E2F0"
  disabled-text: "#8C87B9"
typography:
  title:
    fontFamily: Barlow Condensed
    fontWeight: 800
    fontSize: 32px
  heading:
    fontFamily: Barlow
    fontWeight: 700
    fontSize: 18px
  body:
    fontFamily: Barlow
    fontWeight: 400
    fontSize: 14px
  label:
    fontFamily: Barlow
    fontWeight: 600
    fontSize: 12px
    letterSpacing: 0.12em
  button:
    fontFamily: Barlow
    fontWeight: 600
    fontSize: 15px
  log:
    fontFamily: monospace
    fontWeight: 400
    fontSize: 12px
rounded:
  card: 8px
  button: 8px
spacing:
  xxs: 4px
  xs: 8px
  sm: 12px
  md: 16px
  lg: 20px
  xl: 24px
  section: 32px
---

# Design

Both the Windows patcher and the Android patcher follow this file. It sets how they look and how
their screens are laid out; it does not set what they do. Where a patcher cannot draw something,
the **Windows fallback** or **Android note** under that rule says what it draws instead.

## Reference

The look comes from the game's website, https://wxq.qq.com, as rendered on 2026-10-17. The site
builds its look from images (glass cards, gradients, buttons), so the colours were sampled from
screenshots, not read from its CSS. Its blue `#0000EE` is the browser's default link colour, not a
brand colour.

Only the feel is taken. Nothing is copied from the site: no artwork, character, logo, image or font
file, and no game asset. The patchers are unofficial and must not look like a Tencent product.

## Theme

Light only. A dark theme, when it comes, goes to both patchers at once.

## Colour roles

| Role | Value | Use |
|---|---|---|
| Page | gradient `page-top` → `page-bottom`, top to bottom | the window or screen background |
| Card | `card` with a 1 px `card-edge` | every content card |
| Ink | `ink` | headings and body text on the page and cards |
| Muted text | `text-muted` | supporting text, captions, eyebrow labels |
| Panel | gradient `panel-top` → `panel-bottom` | the hero and confirmation dialogs |
| On panel | `on-panel`, `on-panel-muted` | text on a panel |
| Primary button | panel gradient, `on-panel` text | Start and the main action of a card |
| Confirm button | gradient `confirm-left` → `confirm-right`, left to right, `ink` text | the confirm action on a panel (dialogs) |
| Secondary button | `card` fill, `ink` text, 1 px `ink` edge at 30 % | Cancel, technical tools, Change… |
| Warning | `warning` accents on `warning-surface` | recovery, data-loss consent, storage shortfall |
| Error | `error` accents on `error-surface` | a failed run, a danger confirmation |
| Disabled | `disabled-fill`, `disabled-text` | any disabled button or locked choice |

`warning` is the site's amber tag colour. The site shows no error state; `error` and
`error-surface` are **patcher-only**, added because a patcher has to show failure.

Never put an ice-blue confirm button on the lavender page: it is too pale there. It belongs on a
panel, as on the site.

**Windows fallback.** CustomTkinter has no transparency. Cards use `card-solid` (the card composited
over the page) with a 1 px `#E4E3F2` edge, and the page is a flat `page-top`. The gradients appear
only in the hero image and the dialog panel image, which are drawn locally at startup.

## Shape

Cards and buttons have 8 px corners. Nothing else is rounded. Depth comes from colour (glass on
lavender, indigo panels), never from drop shadows. The site's cut-corner confirm button is not used.

## Type

Barlow (SIL Open Font License) for all interface text, Barlow Condensed ExtraBold for the hero title.
Both are bundled from `resources/fonts/`. The site's own font, HYQiHei, is commercial and is not
shipped. The game's Chinese name, 王者万象棋, uses the system CJK font (Microsoft YaHei on Windows,
the system font on Android). Logs use the system monospace font.

Eyebrow labels (`LANGUAGE`, `DEVICE`, `LOG`) are `label`, upper case, in `text-muted`. Text scales
with the system font size on Android and with display scaling on Windows; layouts must survive both.

## Layout

One column, centred, at most 720 px wide on Windows; full width less 16 px gutters on Android.
Top to bottom:

1. **Hero** — a panel. Eyebrow `COMMUNITY PATCHER  /  HOK ACE` in `on-panel-muted`, the app title in `title`,
   one line saying it is an unofficial, partial translation and that login goes through *Scan to
   login*. Drawn locally: the panel gradient plus a few faint diagonal light bands. No images.
2. **① Language** — a card with, in order: the title, the language note, the two choices (English
   and Bahasa Indonesia), then **Remove translation**, a secondary outlined button.
   - The language note has two variants: no clear is needed while the patcher keeps a pristine
     delta; otherwise the game's data must be cleared first.
   - Remove translation shows only while a pristine delta is kept (Windows: in its working folder).
   - The choices and Remove translation lock together while work runs, in the disabled colours.
3. **② Start** — a card with the single Start button. It rewrites itself in place for each state:
   - **Idle** and **not ready**: the Start button, with the blocker as the next step when there is one.
   - **Running**: a bar and one line, `Step N of M · <step>`, in place of the button.
   - **Result**: a heading, one summary line, the run's own counts as a short list and, where the
     translation was added or removed, the Scan to login note. The result states are
     *Translation added*, *Translation removed*, *Translation written* (Android: recovery closed a
     run whose translation is on the phone, unconfirmed) and *Space freed* (Android).
   - **Notice**: one `text-muted` line under the card's instruction, such as "Access was not
     allowed. Tap Start to try again." It is not a card, and the next notice replaces it.

   **Windows**: device status and the working folder (with its free space and Change…) sit above
   the Start button in this card.
4. **Warning or error card**, directly under ② Start, when one exists:
   - The **warning card** holds anything that needs action. On Android it is "Game won't open?",
     with the recovery options folded and Restore interrupted patch first.
   - The **error card** holds the cause and the next step, with *Copy error details* (Android) and
     *Save log for help*.
5. **Log** — the live activity log; on Android also the technical log. Each log scrolls inside its
   own height-bounded panel while the page scrolls outside it.
6. **Footer** — the installed version, then one row of text buttons: *Technical tools*, *Check for
   updates* and, on Android, *Free up space*. They are not full-width buttons.

Warnings and recovery messages never appear as extra steps.

## Components

**Buttons.** Primary buttons fill the card width. Minimum height 60 dp on Android, 44 px on Windows.
Disabled buttons use the disabled colours and are never only dimmed.

**Dialogs.** A panel with a heading in `on-panel`, the message in `on-panel-muted`, the confirm
button on the right and a secondary Cancel on the left. A danger confirmation (data loss) uses an
`error` confirm button instead of ice-blue. Consent checkboxes start unchecked.

Remove translation and Free up space confirm with a plain dialog, not a danger one: neither
deletes the game's data. The Android Remove translation dialog keeps its consent checkbox.
Free up space's optional "also remove the saved game apps" checkbox starts unchecked and states the
space the next patch will need.

**Progress.** The bar's track is `disabled-fill`, its fill `ink`.

**Android note.** System bars, the launch background and native dialog accents use `page-top` and
`ink`. Scroll content respects the system-bar insets on edge-to-edge Android versions.

## Wording and language

Every user-facing string comes from `resources/ui/strings.json`, in English and Indonesian, and both
patchers use the same string for the same thing. The language choice in ① also sets the interface
language, and switching it while idle redraws the screen at once. Protocol keys, technical tool
names, durable records and raw technical logs are never translated. Both languages keep the same
consent checkboxes and data-loss warnings. Say "translation", never "English", where either language
is meant.

## Tokens

The values above are the source; `resources/ui/theme.json` carries them for both patchers and must
match this file's front matter.
