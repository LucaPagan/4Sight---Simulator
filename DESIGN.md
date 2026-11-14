---
name: Audience Simulator
description: A light-theme operations tool that speaks like a 1960s Italian Olivetti advertisement: full blue fields, geometric marks, one red for the next action.
colors:
  ground: "#F3F5F7"
  surface: "#FFFFFF"
  ink: "#1B1D21"
  ink-secondary: "#4A515B"
  line: "#D5DAE0"
  field-line: "#7C8796"
  olivetti-blue: "#14357A"
  blue-tint: "#E6ECF7"
  action-red: "#D42B21"
  action-red-dark: "#AE1F17"
  red-tint: "#FBE3E1"
  error-ink: "#7A150F"
  amber-tint: "#FFF1CC"
  amber-ink: "#6B4A00"
  mark-amber: "#F0A300"
  mark-green: "#2E8B6A"
  ready-green: "#6FD3A8"
typography:
  display:
    fontFamily: "Jost, system-ui, sans-serif"
    fontSize: "2.75rem"
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: "-0.015em"
  headline:
    fontFamily: "Jost, system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 600
    lineHeight: 1.3
  title:
    fontFamily: "Jost, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 600
    lineHeight: 1.5
  body:
    fontFamily: "Jost, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Jost, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 500
    lineHeight: 1.5
rounded:
  sm: "4px"
  md: "6px"
  pill: "14px"
spacing:
  s1: "4px"
  s2: "8px"
  s3: "12px"
  s4: "16px"
  s5: "24px"
  s6: "32px"
  s7: "48px"
  s8: "64px"
components:
  button-primary:
    backgroundColor: "{colors.action-red}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
    padding: "0 24px"
    height: "48px"
  button-primary-hover:
    backgroundColor: "{colors.action-red-dark}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.olivetti-blue}"
    rounded: "{rounded.sm}"
    padding: "0 24px"
    height: "48px"
  button-secondary-hover:
    backgroundColor: "{colors.blue-tint}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.olivetti-blue}"
    rounded: "{rounded.sm}"
    height: "48px"
  rail:
    backgroundColor: "{colors.olivetti-blue}"
    textColor: "{colors.surface}"
    width: "240px"
    padding: "32px 16px"
  nav-link-active:
    backgroundColor: "{colors.action-red}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
    height: "44px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "12px"
    height: "48px"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.md}"
    padding: "24px"
  badge:
    backgroundColor: "{colors.blue-tint}"
    textColor: "{colors.olivetti-blue}"
    rounded: "{rounded.pill}"
    height: "28px"
---

# Design System: Audience Simulator

## Overview

**Creative North Star: "The Olivetti Advertisement"**

An operations tool for a non-technical marketer comparing Meta ad creatives before spending, used in short daylight office sessions. It borrows the grammar of 1960s Italian corporate advertising: large flat fields of deep blue, plain geometry, a geometric sans, and a single red reserved for the thing the person should do next. It is a light theme throughout; the blue carries structure and identity, not mood.

Density is calm and form-like. Surfaces are white sheets on a cool pale ground, separated by 1px hairlines, never by shadow. Each creative owns a fixed geometric mark (circle, square, triangle, diamond) that recurs in the form, chart, verdict and list, so A versus B is legible by shape and not by color alone.

**Key Characteristics:**
- Full-bleed blue rail on the left, 240px; blue titles; blue for every selected state.
- Red appears only on the primary button, the active nav entry, and error surfaces.
- One typeface (Jost), tabular numerals on every figure.
- 1px hairlines, 4px and 6px radii, no decorative shadows.
- Geometric creative marks as the system's one signature.

## Colors

A cool pale ground and white sheets, one saturated blue, one red, and a small set of mark colors that exist only to tell creatives apart.

### Primary
- **Olivetti Blue** (#14357A): the rail, h1 and link color, selected states, progress fill, focus outline, text selection, and mark A (circle).

### Secondary
- **Action Red** (#D42B21): the primary button, the active rail entry, the text caret. Hover deepens to **Pressed Red** (#AE1F17).

### Tertiary
- **Mark Amber** (#F0A300): mark B (square) and the "to verify" status dot.
- **Mark Green** (#2E8B6A): mark C (triangle). Mark D (diamond) uses Ink.

### Neutral
- **Cool Ground** (#F3F5F7): page background and code blocks.
- **Sheet White** (#FFFFFF): cards, inputs, tables, dialog.
- **Ink** (#1B1D21): body text. **Slate Ink** (#4A515B): secondary text, hints, table heads.
- **Hairline** (#D5DAE0): all dividers and card borders. **Field Stroke** (#7C8796): input and choice-card borders, scrollbar thumb.
- **Blue Wash** (#E6ECF7): selected rows and choice cards, winner row, badges, hover on secondary controls.
- **Red Wash** (#FBE3E1) with **Error Ink** (#7A150F): alerts, error banners, "bad" badges. **Amber Wash** (#FFF1CC) with **Amber Ink** (#6B4A00): warnings, "waiting" badges.

### Named Rules
**The One Red Rule.** Red marks the next action or a fault, nothing else. Titles, selection and emphasis are blue.
**The Shape-Before-Color Rule.** A creative is identified by its mark shape first; its color is secondary and must never be the only cue.

## Typography

**Display Font:** Jost (self-hosted `Jost-latin.woff2`, weights 400-700, `system-ui, sans-serif` fallback)
**Body Font:** Jost
**Label/Mono Font:** Jost for labels; `ui-monospace` only inside `pre` (13px)

**Character:** A geometric sans with Futura-era proportions, set in sentence case and used at modest weights (400, 500, 600). All hierarchy comes from size and weight, never from uppercase or tracking.

### Hierarchy
- **Display** (600, clamp(2rem, 1.4rem + 1.8vw, 2.75rem), 1.1, -0.015em, blue): the single h1 per page.
- **Headline** (600, 1.25rem, 1.3): h2 section titles; card h2 at 1.125rem.
- **Title** (600, 1rem): h3, disclosure summaries (blue), table totals.
- **Body** (400, 1rem, 1.5): default; lead paragraph 1.125rem in Slate Ink, max 62ch.
- **Label** (500, 0.9375rem): field labels, nav links (500, 1rem), step labels. Hints and notes are 0.875rem Slate Ink, the smallest size in use.

### Named Rules
**The Tabular Rule.** Any figure (CTR, CPM, budget, counts) uses tabular numerals.
**The Sentence-Case Rule.** No uppercase, no letter-spaced small caps. The only tracking is the h1 tightening and the wordmark's +0.01em.

## Layout

Two-column shell: a 240px sticky blue rail and a fluid stage (max 1280px) padded 48px by 64px. Content pages cap at 820px; the new-simulation flow is a main column (max 860px) beside a sticky 300px summary aside with a 64px gap. Spacing runs on a 4/8/12/16/24/32/48/64 scale; forms use a two-column grid with 16px by 24px gaps; major sections are separated by 48px.

Responsive: at 1100px the aside drops beneath the form and padding shrinks. At 800px the rail becomes a fixed bottom bar of four stacked icon-and-label tabs (64px tall, safe-area aware), all grids collapse to one column, step numerals hide, and the stage reserves 104px at the bottom. Touch targets are at least 44px; inputs and buttons 48px.

## Elevation & Depth

Flat. Depth comes from white sheets on the cool ground, 1px hairlines, and Blue Wash fills. There are no drop shadows. The only box-shadow in the build is an inset ring that thickens a selected choice card (1.5px) or selected tab (2px) in blue. The dialog is separated by a 55% ink backdrop.

### Named Rules
**The Hairline Rule.** Separate with a 1px Hairline or a tint, never a shadow.

## Shapes

Quiet and rectilinear: 4px for buttons, inputs, tabs and rows; 6px for cards, panels, the chart and the dialog; full pill-ish 14px only for badges and the winner chip; circles for step numerals, status dots and mark A. Creative marks are inline SVG at 18px: circle, square, triangle, diamond. Steps are drawn as 4px top rules, blue when current or done.

## Components

### Buttons
- **Shape:** 4px radius, 48px min height, 24px side padding, 2px transparent border, weight 600, 0.15s background and border transition.
- **Primary:** Action Red fill, white text; hover Pressed Red. One per view.
- **Secondary:** white fill, blue text, 2px blue border; hover Blue Wash.
- **Ghost:** transparent, blue text; hover Blue Wash. **Disabled:** 45% opacity.
- **Focus:** 3px blue outline, 2px offset (white on the rail).

### Navigation
Blue rail with a two-line wordmark, four entries (44px, 20px lucide icon plus label, weight 500). Hover is a 12% white wash; the active entry is filled Action Red. An engine-status link at the bottom is separated by a 30% white rule and carries a 10px dot (amber, or mint when ready). On phones it becomes the bottom bar.

### Inputs / Fields
White fill, 1px Field Stroke border, 4px radius, 48px height, 12px padding, label above at 500 weight. Focus turns the border blue and adds a 3px Blue Wash ring. Native checkboxes, radios and ranges take blue accent; caret is red.

### Cards / Containers
White, 1px Hairline border, 6px radius, 16-24px padding, no shadow. A card never contains another bordered card; inner grouping uses hairline rules or disclosure.

### Choice cards and Tabs
Choice cards are bordered white tiles in a three-column grid; selected gets Blue Wash, blue border and a 1.5px inset ring. Tabs sit in a bordered white tray; the selected tab gets Blue Wash, blue text, 2px inset ring.

### Tables and rows
Full-width white tables, hairline row dividers, Slate Ink 0.875rem headers, right-aligned tabular figures, the winning row in Blue Wash with a blue "winner" chip. List rows are 64px minimum with a Blue Wash hover.

### Creative Mark (signature)
An 18px inline SVG shape per creative, index modulo four: circle in blue, square in amber, triangle in green, diamond in ink. Shown beside the creative name in the form legend, tabs, chart, verdict and list.

### Disclosure, badges, alerts
Disclosure summaries are 600 weight blue with a top hairline. Badges are 28px pills (blue default, amber waiting, red bad). Alerts and error banners are Red Wash blocks with Error Ink; warnings are Amber Wash.

## Do's and Don'ts

### Do:
- **Do** reserve Action Red for the single primary button, the active nav entry, and errors.
- **Do** pair every creative color with its mark shape and keep the shape-to-index mapping fixed.
- **Do** use tabular numerals for every metric and keep text at 14px (0.875rem) or larger.
- **Do** separate surfaces with 1px Hairline borders and Blue Wash fills; keep radii at 4px or 6px.
- **Do** keep body copy in sentence case Jost at 400-600 weight.

### Don't:
- **Don't** add drop shadows or glows; the inset selection ring is the only box-shadow.
- **Don't** put a colored side stripe thicker than 1px on any card or row.
- **Don't** nest a bordered card inside a bordered card.
- **Don't** use blue for errors or red for selection or emphasis.
- **Don't** add eyebrow or kicker labels above titles, or uppercase tracked text.
