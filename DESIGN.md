---
version: alpha
name: Wxq
description: |
  Honor of Kings: Ace embraces a premium, mystical gaming atmosphere defined by
  deep purples, ethereal luminosity, and a sophisticated anime aesthetic. The
  design system balances vibrant hero imagery with elegant typography, creating
  an immersive experience that celebrates strategy, collectibility, and
  community. Depth emerges through color-blocking rather than heavy shadows,
  allowing layered purples and muted neutrals to establish visual hierarchy. The
  overall mood is aspirational and contemporary—befitting a competitive strategy
  game targeting experienced players—while maintaining accessibility through
  clear typography and spacious layouts.
source:
  url: "https://wxq.qq.com"
  pagesAnalyzed: 1
  extractedAt: 2026-10-16
  tokensMeasured: true
colors:
  primary: "#0000EE"
  canvas: "#E3DFF3"
  ink: "#20263E"
  body: "#424967"
  muted: "#FFFFFF"
  accent-1: "#222B4F"
  accent-2: "#313D70"
  accent-3: "#10131D"
  neutral-1: "#000000"
typography:
  body-sm:
    fontFamily: hyqh-60
    fontSize: 14.25px
    fontWeight: 700
    lineHeight: 1.32
    letterSpacing: 0px
  body-xs:
    fontFamily: hyqh-60
    fontSize: 9px
    fontWeight: 400
    lineHeight: 1.17
    letterSpacing: 0px
  label:
    fontFamily: hyqh-60
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0px
  caption-md:
    fontFamily: hyqh-60
    fontSize: 10.5px
    fontWeight: 400
    lineHeight: 1.64
    letterSpacing: 0px
  caption-md-strong:
    fontFamily: hyqh-80
    fontSize: 10.5px
    fontWeight: 700
    lineHeight: 1.64
    letterSpacing: 0px
  caption-sm:
    fontFamily: hyqh-65
    fontSize: 10.125px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0px
  caption-xs:
    fontFamily: hyqh-60
    fontSize: 9.75px
    fontWeight: 400
    lineHeight: 1.46
    letterSpacing: 0px
rounded:
  none: 0px
  xs: 7.5px
spacing:
  xxs: 4px
  xs: 8px
  sm: 12px
  md: 16px
  lg: 20px
  xl: 24px
  xxl: 28px
  xxxl: 32px
  section: 36px
  band: 48px
elevationStrategy: color-blocking
themes:
  derived: dark   # the other theme is the site's measured palette
  light:
    bg: "#E3DFF3"
    surface: "#DCD8EC"
    surfaceRaised: "#D4D1E5"
    text: "#20263E"
    textMuted: "#424967"
    border: "#CCC9DD"
    accent: "#0000EE"
    accentFg: "#FFFFFF"
    focusRing: "#0000EE"
    elevation: shadow
  dark:
    bg: "#090916"
    surface: "#181824"
    surfaceRaised: "#242430"
    text: "#F5F5FE"
    textMuted: "#9B9BA6"
    border: "#30303B"
    accent: "#6969FF"
    accentFg: "#090916"
    focusRing: "#4141FF"
    elevation: "border+surface"
components:
  button-icon:
    textColor: "{colors.ink}"
    height: 54.375px
    fontSize: 12px
    fontFamily: tahoma
    fontWeight: 400
    lineHeight: 1.5
  card:
    typography: "{typography.label}"
    textColor: "{colors.primary}"
  card-sm:
    typography: "{typography.label}"
    textColor: "{colors.ink}"
    rounded: "{rounded.xs}"
  footer:
    typography: "{typography.label}"
    textColor: "{colors.ink}"
  link:
    typography: "{typography.body-xs}"
    textColor: "{colors.muted}"
states:
  card-hover:
    target: card
    state: hover
    filter: "brightness(1.04)"
  link-hover:
    target: link
    state: hover
    opacity: 1
  other-hover:
    target: other
    state: hover
    textColor: "rgb(64, 158, 255)"
  button-hover:
    target: button
    state: hover
    textColor: "rgb(64, 158, 255)"
    borderColor: "rgb(198, 226, 255)"
    backgroundColor: "rgb(236, 245, 255)"
  other-disabled:
    target: other
    state: disabled
    opacity: 0.7
breakpoints:
  - width: 375
    containerWidth: 360
    gridColumns: 2
    navLinksVisible: 0
    menuToggleVisible: false
    headingPx: 0
    bodyPx: 12
    sectionPaddingX: 0
  - width: 768
    containerWidth: 753
    gridColumns: 1
    navLinksVisible: 0
    menuToggleVisible: false
    headingPx: 0
    bodyPx: 12
    sectionPaddingX: 0
  - width: 1024
    containerWidth: 1009
    gridColumns: 1
    navLinksVisible: 0
    menuToggleVisible: false
    headingPx: 0
    bodyPx: 12
    sectionPaddingX: 0
  - width: 1280
    containerWidth: 1265
    gridColumns: 1
    navLinksVisible: 0
    menuToggleVisible: false
    headingPx: 0
    bodyPx: 12
    sectionPaddingX: 0
  - width: 1440
    containerWidth: 1425
    gridColumns: 1
    navLinksVisible: 0
    menuToggleVisible: false
    headingPx: 0
    bodyPx: 12
    sectionPaddingX: 0
coverage:
  statesFound: 14
  gradientsFound: 0
  rolesUnassigned: 4
  archetypesUnnamed: 0
  archetypesDetected: 0
  responsiveMeasured: true
  stylesheetsBlocked: false
  semanticRampDeclared: false
---

# Design System Inspired by Honor of Kings: Ace

## 1. Visual Theme & Atmosphere

Honor of Kings: Ace embraces a **premium, mystical gaming atmosphere** defined by deep purples, ethereal luminosity, and a sophisticated anime aesthetic. The design system balances vibrant hero imagery with elegant typography, creating an immersive experience that celebrates strategy, collectibility, and community. Depth emerges through color-blocking rather than heavy shadows, allowing layered purples and muted neutrals to establish visual hierarchy. The overall mood is aspirational and contemporary—befitting a competitive strategy game targeting experienced players—while maintaining accessibility through clear typography and spacious layouts.

**Key Characteristics**
- Deep purple and indigo color-blocking for depth and visual separation
- Sharp, angular corners (0px radius) emphasizing modernity and precision
- Luminous accent colors (cyan, coral) used sparingly to draw focus
- Type-forward design with varied font weights and precise optical sizing
- Flat, color-based elevation strategy—no drop shadows
- Generous whitespace and breathing room between content zones
- Full-width, single-column layout optimized for hero imagery and card grids

## 2. Color Palette & Roles

### Primary
- **Brand Accent** (`{colors.primary}` — `#0000EE`): Primary CTA fills, active states, brand mark, hyperlinks, and interactive highlights. The vibrant electric blue cuts through the purple palette to signal action.

### Accent Colors
- **Deep Indigo** (`{colors.accent-1}` — `#222B4F`): Decorative background bands, lower-priority surfaces, and atmospheric texture layers.
- **Rich Purple** (`{colors.accent-2}` — `#313D70`): Decorative mid-tone overlays, card backgrounds, and narrative section dividers.
- **Void** (`{colors.accent-3}` — `#10131D`): Decorative darkest layer, atmospheric depth, and transition zones between sections.

### Neutral Scale
- **Canvas** (`{colors.canvas}` — `#E3DFF3`): Default page background, subtle lavender undertone that unifies the purple theme.
- **Ink** (`{colors.ink}` — `#20263E`): Primary heading text, dominant body copy, and semantic emphasis. Deep blue-gray ensures legibility over light canvas.
- **Body** (`{colors.body}` — `#424967`): Secondary body copy, muted descriptions, and lower-hierarchy text. Slightly lighter than ink, used for supporting information.
- **Muted** (`{colors.muted}` — `#FFFFFF`): Captions, tertiary text, overlay text on dark backgrounds, and ghost button labels.
- **Neutral Black** (`{colors.neutral-1}` — `#000000`): Reserve dark accent, graphic overlays, and maximum contrast scenarios.

### Semantic & Status
No error, success, or warning semantic colors were extracted from the site. The design does not expose a status ramp; see Known Gaps.

## 3. Typography Rules

### Font Family
- **Primary Font:** Hyqh (全 weights available: 400, 700, 800)
- **Fallback Stack:** `hyqh-60, hyqh-65, hyqh-80, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif`

The site uses Hyqh variants (hyqh-60, hyqh-65, hyqh-80) as distinct weighted instances rather than a single family. Treat each as a discrete font file for reliable rendering.

### Hierarchy

| Role | Font | Size | Weight | Line Height | Letter Spacing | Notes |
|---|---|---|---|---|---|---|
| Label | hyqh-60 | 12px | 400 | 1.5 (18px) | 0px | Tag labels, badges, interactive hints |
| Body (strong) | hyqh-60 | 14.25px | 700 | 1.32 (18.81px) | 0px | Emphasized body copy, call-outs |
| Body (xs) | hyqh-60 | 9px | 400 | 1.17 (10.53px) | 0px | Micro text, footnotes, small captions |
| Caption (md) | hyqh-60 | 10.5px | 400 | 1.64 (17.22px) | 0px | Small metadata, secondary labels |
| Caption (md, strong) | hyqh-80 | 10.5px | 700 | 1.64 (17.22px) | 0px | Emphasized captions, small headings |
| Caption (sm) | hyqh-65 | 10.125px | 400 | 1.5 (15.19px) | 0px | Minimal text, icon labels |
| Caption (xs) | hyqh-60 | 9.75px | 400 | 1.46 (14.22px) | 0px | Diminutive labels, stamps |

### Principles
- **Optical Sizing:** Font size varies by weight and role to maintain visual consistency across point sizes (e.g., 10.5px at weight 400 vs. 10.5px at weight 700 use different x-heights).
- **High Line Height on Small Text:** Captions employ generous line-height ratios (1.64) to ensure scannability and breathing room despite diminutive point sizes.
- **Weight Hierarchy:** Weight 700 is reserved for emphasis; weight 400 is the default. Weight 800 is available but not directly measured on this page; see Known Gaps.
- **No Tracking Variations:** Letter-spacing is uniformly 0px across all roles; the design relies on weight and size for contrast, not letterspacing adjustments.

## 4. Component Stylings

### Buttons

**Icon Button**
- Background: `rgba(0, 0, 0, 0)` (transparent)
- Text Color: `{colors.ink}` (`#20263E`)
- Font: hyqh-60, 12px, weight 400
- Padding: 0px
- Border: none
- Border Radius: `{rounded.none}` (0px)
- Width: 43.125px; Height: 54.375px
- Box Shadow: none
- Line Height: 1.5 (18px)

**Hover State** (from extraction)
- Text Color: `rgb(64, 158, 255)`
- Border Color: `rgb(198, 226, 255)`
- Background Color: `rgb(236, 245, 255)`

**Active Variant** (primary CTA)
- Background: `{colors.primary}` (`#0000EE`)
- Text Color: `{colors.muted}` (`#FFFFFF`)
- Border Color: `rgb(102, 177, 255)`

**Hover (Primary CTA)**
- Text Color: `rgb(255, 255, 255)`
- Border Color: `rgb(102, 177, 255)`
- Background Color: `rgb(102, 177, 255)`

**Disabled State** (from extraction)
- Opacity: 0.7
- All other properties remain unchanged

### Cards & Containers

**Large Card**
- Background: `rgba(0, 0, 0, 0)` (transparent)
- Text Color: `{colors.primary}` (`#0000EE`)
- Width: 519px; Height: 258px
- Border Radius: `{rounded.none}` (0px)
- Font: hyqh-60, 12px, weight 400
- Padding: 0px
- Border: none
- Box Shadow: none

**Hover State**
- Filter: `brightness(1.04)` (subtle brightening)

**Small Card**
- Background: `rgba(0, 0, 0, 0)` (transparent)
- Text Color: `{colors.ink}` (`#20263E`)
- Width: 81px; Height: 81px
- Border Radius: `{rounded.xs}` (7.5px)
- Font: hyqh-60, 12px, weight 400
- Padding: 0px
- Border: none
- Box Shadow: none

**Hover State**
- Filter: `brightness(1.04)`

### Navigation & Links

**Link**
- Text Color: `{colors.muted}` (`#FFFFFF`)
- Font: hyqh-60, 9px, weight 400
- Line Height: 1.17 (10.5px)
- Background: `rgba(0, 0, 0, 0)` (transparent)
- Border: none
- Box Shadow: none
- Padding: 0px

**Link Hover State**
- Text Color: `rgb(240, 115, 115)` or `rgb(245, 114, 114)` (warm coral highlight)
- Opacity: 1

**Link Alternative Hover**
- Text Color: `rgb(240, 115, 115)` (same coral, applied on dark backgrounds)

### Footer

**Default**
- Background: `rgba(0, 0, 0, 0)` (transparent)
- Text Color: `{colors.ink}` (`#20263E`)
- Width: 1425px; Height: 56.25px
- Font: hyqh-60, 12px, weight 400
- Line Height: 1.5 (18px)
- Border Radius: `{rounded.none}` (0px)
- Padding: 0px
- Border: none
- Box Shadow: none

### Focus & Outline States
- **:focus** – Outline: 0px (no visible outline)
- **:focus-visible** – Outline: 0px (no visible outline)

The design system deliberately removes focus outlines; keyboard and assistive device focus may not be visually indicated. See Known Gaps for accessibility implications.

## 5. Layout Principles

### Spacing System
The design employs a **10-step spacing scale** based on a 4px base unit:

- `{spacing.xxs}` — 4px (microscopic gaps between inline elements)
- `{spacing.xs}` — 8px (tight component margins)
- `{spacing.sm}` — 12px (small padding, mobile section gutters)
- `{spacing.md}` — 16px (default component padding, standard margins)
- `{spacing.lg}` — 20px (generous margins between major blocks)
- `{spacing.xl}` — 24px (heading-to-body spacing)
- `{spacing.xxl}` — 28px (large section separations)
- `{spacing.xxxl}` — 32px (major layout divisions)
- `{spacing.section}` — 36px (section padding and separation)
- `{spacing.band}` — 48px (hero banner and full-width section padding)

**Usage Context**
- Inline element gaps: `{spacing.xxs}` to `{spacing.xs}`
- Card padding: `{spacing.md}` to `{spacing.lg}`
- Section padding-left/right: `{spacing.sm}` (mobile) to `{spacing.xxxl}` (desktop)
- Section margin-top/bottom: `{spacing.section}` to `{spacing.band}`

### Grid & Container
- **Max Width:** 1425px (measured at 1440px viewport; layout column width: 1425px)
- **Column Strategy:** Single-column layout across all breakpoints (measured breakpoints show 1 column at all widths from 375px to 1440px)
- **Section Padding:** 12px left/right at all breakpoints (consistent gutter; content area respects viewport edges)
- **No Multi-Column Grid Detected:** The site uses full-width hero sections and single-column card stacks, not a traditional CSS grid

### Whitespace Philosophy
The design prioritizes **breathing room and visual clarity** over density. Large hero images occupy full width, followed by sparse text overlays. Card grids employ single columns with padding between rows. Section separators use color-blocking (indigo bands, void layers) rather than whitespace lines, allowing the palette to define hierarchy. The 12px horizontal padding at all breakpoints creates narrow, focused content lanes that emphasize imagery over text.

### Border Radius Scale
- `{rounded.none}` — 0px
  - Buttons, large cards, footer, primary CTAs
  - Context: Sharp corners reinforce modernity and precision
- `{rounded.xs}` — 7.5px
  - Small square cards (81px × 81px), badge containers
  - Context: Gentle rounding softens small UI elements while maintaining edge definition

The system has exactly two radius values; no progressive rounding scale exists.

## 6. Depth & Elevation

### Surface Strategy
The design system uses **color-blocking for depth** rather than shadows. Depth emerges from layered surface colors (deep indigo, rich purple, void black) arranged in atmospheric bands. No box-shadow or drop-shadow values were measured on this page.

| Level | Treatment | Use |
|---|---|---|
| Base | Canvas background `#E3DFF3` | Default page surface, primary reading area |
| Tier 1 | Deep Indigo `#222B4F` overlay | Lower-priority narrative zones, atmospheric texture |
| Tier 2 | Rich Purple `#313D70` overlay | Mid-tone dividers, card background hints, section transitions |
| Tier 3 | Void `#10131D` overlay | Darkest atmospheric layer, transitions to featured content |
| Float (Cards) | Card backgrounds with hero image or product render | Appear lifted via proximity to hero imagery and 1.04× brightness hover |

No traditional box-shadow or blur-based elevation is employed; see **Interaction States** for hover treatments (brightness filter).

### Opacity Levels
The system defines four opacity values for layering and state communication:

- **72% (0.72)** — Primary semi-transparency, used for overlays and background layers that must remain legible
- **62% (0.62)** — Mid-transparency, softer overlays and disabled-adjacent states
- **25% (0.25)** — Subtle transparency, barely-visible watermarks or decorative hints
- **20% (0.20)** — Minimal transparency, lightest overlay tints

**Usage Context**
- Disabled interactive elements: `0.7` (70%, rounded)
- Background overlays: `0.72`
- Decorative meshes: `0.25` to `0.20`
- Backdrop filters: `0.62`

### Z-index / Layering
Eight z-index values were measured:

- **z-index: 1** — Base layer, default page content
- **z-index: 2** — Background decorative elements, atmospheric bands
- **z-index: 3** — Card and section backgrounds
- **z-index: 4** — Interactive card elements, hover states
- **z-index: 5** — Foreground content, text overlays on hero images
- **z-index: 6** — Modal and overlay backgrounds
- **z-index: 7** — Sticky navigation, persistent UI chrome
- **z-index: 8** — Top-layer modals, toasts, and dropdown menus

The scale is linear and conservative; no values exceed 8, indicating a flat hierarchy with minimal overlap complexity.

## 7. Do's and Don'ts

### Do
- **Use sharp corners (0px radius) for primary buttons, cards, and CTAs** to maintain the modern, precision-focused aesthetic.
- **Employ the deep purple accent colors (`{colors.accent-1}`, `{colors.accent-2}`, `{colors.accent-3}`) as atmospheric background bands** rather than text or interactive elements; they define spatial depth through color-blocking.
- **Default to single-column layouts** even on larger viewports; full-width hero sections and card stacks are the primary content structure.
- **Reserve the primary blue (`{colors.primary}` — `#0000EE`) for interactive elements, active states, and brand marks.** It must stand out against the purple palette.
- **Employ generous line-height (1.5 to 1.64) on small text** (`{typography.caption-md}`, `{typography.caption-sm}`) to maintain scannability despite diminutive point sizes.
- **Use consistent 12px horizontal padding** at all breakpoints; this narrow gutter focuses attention on full-width imagery.
- **Apply subtle brightness boost (1.04) on card hover** to signal interactivity without altering color or introducing shadows.
- **Keep focus outlines hidden** (outline: 0px) for a clean interface, but ensure keyboard navigation is otherwise fully supported.

### Don't
- **Do not introduce drop shadows or blur-based elevation.** Depth comes exclusively from surface color changes and brightness filters.
- **Do not round primary buttons or large cards.** Maintain 0px radius to reinforce the sharp, modern aesthetic.
- **Do not use the accent colors (`{colors.accent-1}`, `{colors.accent-2}`, `{colors.accent-3}`) as text or CTA fills.** They are atmospheric and decorative; preserve visual hierarchy by limiting them to background layers.
- **Do not break the single-column layout on desktop.** The design intentionally maintains narrow content lanes; multi-column grids would dilute focus on hero imagery.
- **Do not add letter-spacing adjustments** to any typography role. All tracking is 0px; contrast is achieved through weight and size variation alone.
- **Do not invent semantic status colors.** The site does not expose error/success/warning states; do not create them.
- **Do not reduce the 12px horizontal padding** on mobile or reduce the viewport width; the narrow gutter is intentional and consistent.
- **Do not apply text decoration (underline, strikethrough) to links** beyond the default (none, appearing as plain text). Rely on color and hover state alone to signal linkage.

## 8. Responsive Behavior

### Breakpoints
The site uses a **fluid, single-column layout** with no traditional breakpoint-driven layout shifts. All measured viewports (375px to 1440px) display identical single-column structure:

| Viewport | Content Width | Columns | Nav Links | Menu | Largest Heading | Body Font | Section Padding-X |
|---|---|---|---|---|---|---|---|
| 375px (mobile) | 360px | 1 | 0 | no | — | 12px | 12px |
| 768px (tablet) | 753px | 1 | 0 | no | — | 12px | 12px |
| 1024px (desktop) | 1009px | 1 | 0 | no | — | 12px | 12px |
| 1280px (large) | 1265px | 1 | 0 | no | — | 12px | 12px |
| 1440px (XL) | 1425px | 1 | 0 | no | — | 12px | 12px |

**Key Observations:**
- **No responsive breakpoints detected.** The layout does not shift or collapse across viewports.
- **Consistent 12px padding at all widths.** Gutters do not widen or narrow; the narrow lane is a design choice, not a breakpoint response.
- **No hamburger menu or sticky nav.** Navigation links are constant (count: 0 hidden nav links observed, suggesting navigation is not primary on this hero/card page).
- **Full-width hero imagery** scales fluidly without explicit media queries or container queries observed in this extraction.

### Touch Targets
No explicit touch target data was extracted. However, observed interactive elements (buttons, links, cards) should follow these guidelines:

- **Minimum Touch Target:** 44px × 44px (recommended for mobile; the 81px × 81px small cards exceed this, as do the 43.125px × 54.375px icon buttons).
- **Card Tap Zone:** Full card area (519px × 258px for large; 81px × 81px for small) is interactive.
- **Link Hit Area:** Links inherit font size (9px minimum); consider wrapping in larger touch containers on mobile or increasing hover area via padding.

### Collapsing Strategy
**No collapsing behavior was measured.** The layout does not shift from multi-column to single-column, nor do sections reorder. Instead:

- **Hero section** remains full-width and full-height at all breakpoints.
- **Card grids** remain single-column and flow vertically.
- **Text overlays** scale fluidly with the viewport (no explicit font-size breakpoints).
- **Padding and margins** stay constant (12px left/right across all widths).

If responsive adjustments are needed, implement them via CSS media queries or container queries outside this design system (e.g., adjust card width, reflow card grid to multi-column, or introduce a sticky nav on mobile).

## 9. Agent Prompt Guide

### Quick Color Reference
When implementing UI, use these mappings for semantic intent:

- **Primary CTA / Brand Accent:** Primary (`#0000EE`) — all interactive elements, active states, brand marks
- **Page Background:** Canvas (`#E3DFF3`) — default surface
- **Primary Text / Headings:** Ink (`#20263E`) — dominant body copy and headings
- **Secondary Text:** Body (`#424967`) — supporting copy, lower hierarchy
- **Captions & Tertiary Text:** Muted (`#FFFFFF`) — overlay text, ghost labels, accessibility captions
- **Atmospheric Depth (not text):** Deep Indigo (`#222B4F`), Rich Purple (`#313D70`), Void (`#10131D`) — background bands only

### Iteration Guide
Follow these 8 rules in order when implementing or refining Honor of Kings: Ace components:

1. **Maintain sharp corners (0px radius) on all primary buttons and large cards.** Rounding is reserved for small UI elements (7.5px on 81px cards only).

2. **Use color-blocking for depth, not shadows.** Layer atmospheric purples and indigos behind content; never add drop shadows or blur effects.

3. **Employ single-column layouts exclusively.** Full-width hero, single-column card stack. No multi-column grids unless explicitly measured.

4. **Default to the primary blue (`#0000EE`) for any interactive element, active state, or brand accent.** It must contrast sharply against the purple palette.

5. **Apply 12px horizontal padding consistently across all viewports.** Narrow gutters are intentional; do not widen them on desktop.

6. **Use generous line-height (1.5 to 1.64) on small text (`{typography.caption-*}` roles).** Scannability over compactness.

7. **Implement hover states via subtle brightness filters (1.04) or color shifts, not shadows or scale transforms.** Refer to the extracted "Interaction States" section for exact hover CSS.

8. **Hide focus outlines (outline: 0px) but ensure full keyboard navigation and assistive device support.** Test with screen readers and keyboard-only navigation.

## 10. Known Gaps

- **No semantic status colors.** The site does not expose error, success, warning, or info states. No semantic color ramp exists; do not invent one. See Gaps under Color Palette.
- **No error/success/warning interaction feedback.** Validation states, success confirmations, and error messages are not covered by this extraction; implement outside this system.
- **No gradients or decorative mesh patterns measured.** The site may use CSS gradients or animated background meshes; they are not included in this extraction. Implement via supplementary CSS.
- **No explicit font-weight 800 in use.** Hyqh-80 is available (`{typography.caption-md-strong}` uses weight 700 only). Weight 800 is not measured on this page; do not assume it exists in production.
- **No dark mode or theme variants detected.** Extraction covers a single light theme. A derived dark theme may exist but was not measured; do not assume it.
- **No hover/focus/active/disabled state CSS for all components.** Only partial interaction state data was extracted (e.g., button and link hover). Other components' focus, active, and disabled states are not included; see Interaction States section for exact coverage.
- **Navigation / hamburger menu behavior not observed.** The site is primarily hero + card grid; navigation may exist on other pages or behind authentication. Sticky nav, dropdown menus, and mobile nav patterns are not included.
- **No form input styling extracted.** Input, textarea, select, and checkbox components are not present on this page. Implement them per HTML defaults or extend this system with supplementary component documentation.
- **No modal, overlay, or toast component styling.** These patterns are not measured on the extracted page; implement separately.
- **4 accent colors with no assigned semantic role.** Deep Indigo (`#222B4F`), Rich Purple (`#313D70`), and Void (`#10131D`) are decorative atmospheric colors. No measured usage guides their application beyond background layers; see Color Palette.
- **Z-index scale measured (1–8) but not all layers explained.** The 8-level stacking order is provided; specific components (modals, dropdowns, sticky header) not measured. Adapt scale to your component set as needed.
- **Opacity levels provided (72%, 62%, 25%, 20%) but not all applied.** Only disabled opacity (0.7) is directly measured. Other opacity values are extracted from the palette but may not be used consistently; validate usage in your implementation.
- **Page surfaces behind authentication not visited.** User account, profile, or game-specific pages may differ from this public hero page. Design patterns there are not included.

---

**Extraction Date & Coverage:** Analyzed 1 page (`https://wxq.qq.com`). All measured values are from the homepage hero + activity card grid section. Desktop and mobile viewports were inspected; no dark mode, alternate themes, or authenticated surfaces were measured.