---
name: Product Price Matrix
description: A certificate-of-analysis assay sheet for pricing 596 beauty and personal-care SKUs against the Bangladeshi marketplace.
colors:
  paper: "#fbfbf9"
  sheet: "#ffffff"
  sheet-alt: "#f6f6f3"
  sheet-hover: "#f4f5f1"
  sheet-sunk: "#efefea"
  ink: "#1c2024"
  ink-2: "#454b53"
  ink-3: "#5d636b"
  ink-35: "#666c74"
  ink-4: "#9aa0a7"
  rule-faint: "#f2f0eb"
  rule: "#eceae5"
  rule-2: "#dedcd6"
  rule-3: "#c4c3bb"
  rule-datum: "#a9a89f"
  assay-900: "#0b4d39"
  assay-800: "#08402f"
  assay-700: "#0f6b4f"
  assay-600: "#158a66"
  assay-100: "#d6e9df"
  assay-50: "#edf6f1"
  brass-700: "#78530f"
  spec-700: "#8f1d1d"
  spec-600: "#b32020"
  spec-100: "#eecfcb"
  spec-50: "#fbedec"
  tune-700: "#5b3fa8"
  tune-100: "#e2dcf4"
  tune-50: "#f2eefb"
  chip-mkt-disc-bg: "#e2f0e8"
  chip-mkt-disc-border: "#b5d9c7"
  chip-mkt-disc-text: "#14614a"
  chip-tier1-bg: "#eef4f1"
  chip-tier1-border: "#cee1d8"
  chip-tier1-text: "#2c5f4d"
  chip-tier2-bg: "#e2f0e8"
  chip-tier2-border: "#b5d9c7"
  chip-tier2-text: "#14614a"
  chip-tier3-bg: "#f6eedb"
  chip-tier3-border: "#e3d1a6"
  chip-tier4-bg: "#f6e4da"
  chip-tier4-border: "#e5c1ab"
  chip-tier4-text: "#8a3b14"
  chip-zero-bg: "#f1f1ee"
  chip-zero-border: "#dedcd5"
  chip-zero-text: "#4a4f56"
typography:
  display:
    fontFamily: "Plus Jakarta Sans, Inter, sans-serif"
    fontSize: "19px"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.018em"
  wordmark:
    fontFamily: "Plus Jakarta Sans, Inter, sans-serif"
    fontSize: "13px"
    fontWeight: 800
    letterSpacing: "0.06em"
  title:
    fontFamily: "Inter, sans-serif"
    fontSize: "18px"
    fontWeight: 700
    letterSpacing: "-0.02em"
  reading:
    fontFamily: "Inter, sans-serif"
    fontSize: "17px"
    fontWeight: 700
    letterSpacing: "-0.02em"
    fontFeature: "tnum 1, lnum 1"
  body:
    fontFamily: "Inter, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    lineHeight: 1.32
    letterSpacing: "-0.008em"
  numeric:
    fontFamily: "Inter, sans-serif"
    fontSize: "13.5px"
    fontWeight: 700
    fontFeature: "tnum 1, lnum 1"
  numeric-input:
    fontFamily: "Inter, sans-serif"
    fontSize: "14.5px"
    fontWeight: 600
    fontFeature: "tnum 1, lnum 1"
  control:
    fontFamily: "Inter, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    letterSpacing: "0.01em"
  meta:
    fontFamily: "Inter, sans-serif"
    fontSize: "11.5px"
    fontWeight: 500
  label:
    fontFamily: "Inter, sans-serif"
    fontSize: "10.5px"
    fontWeight: 700
    letterSpacing: "0.09em"
  basis:
    fontFamily: "Inter, sans-serif"
    fontSize: "10px"
    fontWeight: 500
    letterSpacing: "0.02em"
  micro:
    fontFamily: "Inter, sans-serif"
    fontSize: "9px"
    fontWeight: 700
    letterSpacing: "0.05em"
rounded:
  none: "0px"
spacing:
  hairline: "1px"
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "18px"
  xl: "22px"
components:
  button-primary:
    backgroundColor: "{colors.assay-900}"
    textColor: "{colors.sheet}"
    rounded: "{rounded.none}"
    padding: "0 15px"
    height: "46px"
  button-primary-hover:
    backgroundColor: "{colors.assay-700}"
    textColor: "{colors.sheet}"
  button-ghost:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "0 14px"
    height: "34px"
  button-danger:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.spec-700}"
    rounded: "{rounded.none}"
    padding: "0 14px"
    height: "32px"
  button-danger-hover:
    backgroundColor: "{colors.spec-600}"
    textColor: "{colors.sheet}"
  spec-flag:
    backgroundColor: "{colors.spec-50}"
    textColor: "{colors.spec-700}"
    rounded: "{rounded.none}"
    padding: "0 15px"
    height: "46px"
  spec-flag-active:
    backgroundColor: "{colors.spec-600}"
    textColor: "{colors.sheet}"
  input:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "0 11px"
    height: "34px"
  chip-under-cost:
    backgroundColor: "{colors.spec-50}"
    textColor: "{colors.spec-700}"
    rounded: "{rounded.none}"
    padding: "2px 6px"
  chip-healthy:
    backgroundColor: "#e2f0e8"
    textColor: "#14614a"
    rounded: "{rounded.none}"
    padding: "2px 6px"
  chip-out-of-spec:
    backgroundColor: "{colors.spec-600}"
    textColor: "{colors.sheet}"
    rounded: "{rounded.none}"
    padding: "2px 6px"
  chip-edited:
    backgroundColor: "{colors.tune-50}"
    textColor: "{colors.tune-700}"
    rounded: "{rounded.none}"
    padding: "1px 5px"
  chip-tuned:
    backgroundColor: "{colors.tune-50}"
    textColor: "{colors.tune-700}"
    rounded: "{rounded.none}"
    padding: "1px 5px"
---

# Design System: Product Price Matrix

## Overview

**Creative North Star: "The Certificate of Analysis"**

A price recommendation is an assay result, not a dashboard tile. Every SKU on this sheet is a specimen with three readings: a measured value (the recommended selling price), a specification limit (the MRP benchmark), and a set of replicate measurements (what the channels are actually charging). The interface is the lab report those readings are printed on — ruled paper, hairline graphite, and one committed assay green.

The density is deliberate and high: 596 specimens across two books, five pinned columns and up to thirteen channel columns, read down the page rather than scanned as cards. The operator is at a desk, in a pricing review, comparing numbers — so the type scale is fixed rather than fluid, digits are tabular so they align down every column, and nothing animates that does not report a state change. Where a card grid would have been the reflex, the answer here is a rule.

This system explicitly rejects the SaaS admin dashboard it replaced: the generic slate canvas, the sky-blue accent, the rounded card-in-card nesting, the KPI-tile header, the floating pill, and the unicode glyphs standing in for icons. It also refuses the six-unrelated-pastels chip palette — a percentage scale must read as a scale.

**Key Characteristics:**
- Ruled paper, never cards. Structure comes from hairlines, not containers.
- 0px radius everywhere, without exception.
- One committed green for brand, action, and in-spec; one crimson for out-of-spec.
- Tabular lining figures throughout — the sheet is read down its columns.
- Full-bleed density: the data is the page, with no container chrome around it.

## Colors

A warm lab-paper ground under graphite ink, with exactly two semantic colors: assay green for what is healthy and crimson for what has failed.

**Strategy: Restrained.** The operator came to complete a task, so color is reserved for meaning. Green marks the brand, the primary action, and the healthy margin band. Crimson marks a single condition — a recommendation that cannot be sold. Violet marks an operator-set value: either a `TUNED` engine parameter or an `EDITED` raw price. Nothing else in the interface is colored.

| Role | Token | Value | Use |
| --- | --- | --- | --- |
| Paper | `paper` | `#fbfbf9` | The application ground; a warm white, never gray |
| Sheet | `sheet` | `#ffffff` | Cell and dialog surfaces |
| Sheet (alt) | `sheet-alt` | `#f6f6f3` | Column heads, the instrument tier, alternating audit rows |
| Sheet (sunk) | `sheet-sunk` | `#efefea` | Channel cells with no listing; count markers |
| Ink | `ink` | `#1c2024` | Prices, product titles |
| Ink 2 | `ink-2` | `#454b53` | Secondary controls |
| Ink 3 | `ink-3` | `#5d636b` | Column labels, hints, metadata |
| Ink 3.5 | `ink-35` | `#666c74` | Basis lines — the lightest tone still clearing 4.5:1 |
| Ink 4 | `ink-4` | `#9aa0a7` | **Non-text marks only.** Below 4.5:1; never set copy in it |
| Rules | `rule-faint` / `rule` / `rule-2` / `rule-3` | `#f2f0eb` / `#eceae5` / `#dedcd6` / `#c4c3bb` | Column, cell, section, and control boundaries in ascending weight |
| Datum | `rule-datum` | `#a9a89f` | The one line closing the pinned columns |
| Assay green | `assay-900` / `800` / `700` / `600` | `#0b4d39` / `#08402f` / `#0f6b4f` / `#158a66` | Brand, primary action, the selling price, focus rings |
| Assay tint | `assay-100` / `50` | `#d6e9df` / `#edf6f1` | Active-tab counts, the in-spec band on the spread rail |
| Brass | `brass-700` | `#78530f` | The rich-margin chip band; a third-party-average MRP |
| Out of spec | `spec-700` / `600` | `#8f1d1d` / `#b32020` | Failed measurements, the danger zone, the out-of-spec flag |
| Out-of-spec tint | `spec-100` / `50` | `#eecfcb` / `#fbedec` | Banner and flag grounds |
| Operator-set value | `tune-700` / `100` / `50` | `#5b3fa8` / `#e2dcf4` / `#f2eefb` | Per-SKU pinned engine parameters (`TUNED`) and admin-edited Source Cost/MRP (`EDITED`) |

**The chip ramp is an ordered scale, not a set of tags.** Both ends alarm — selling under cost, or so far over it the price will not clear — with the healthy band in assay green at the center, warming through brass as margin gets rich.

| Band | Background | Text | Reads as |
| --- | --- | --- | --- |
| Below cost | `#fbedec` | `#8f1d1d` | Loss |
| At par (0%) | `#f1f1ee` | `#4a4f56` | Neutral |
| +1 to +15% | `#eef4f1` | `#2c5f4d` | Thin |
| +15 to +35% | `#e2f0e8` | `#14614a` | **Healthy** |
| +35 to +60% | `#f6eedb` | `#78530f` | Rich |
| Above +60% | `#f6e4da` | `#8a3b14` | Extreme |
| **Out of spec** | `#b32020` solid | `#ffffff` | **Unsellable** |

Out-of-spec is not a seventh tier. It is a failed measurement and overrides the ramp entirely, wherever a recommended price exceeds its MRP benchmark.

## Typography

One family carries the whole interface. `Inter` sets every label, price, control, and body line; `Plus Jakarta Sans` appears only on the wordmark and modal titles. Monospace is prohibited — this is measurement, not code, and Inter's tabular figures do the alignment work a mono face would otherwise be hired for.

- **Tabular lining figures are the load-bearing decision.** `font-variant-numeric: tabular-nums lining-nums` is set on `body` and re-asserted on every price, chip, count, and input. A sheet read down its columns needs digits of equal width.
- **Fixed rem/px scale, never fluid.** Operators view at a consistent distance and DPI; a heading that shrinks in a narrow pane reads worse, not better. Type sizes hold at every breakpoint — adaptation is structural.
- **Tight ratio.** Steps run 9 / 9.5 / 10 / 10.5 / 11 / 11.5 / 12 / 12.5 / 13 / 13.5 / 14 px, with 17–19px reserved for dialog titles and the record's headline readings. There are many type elements here; exaggerated contrast would be noise. The named roles above map onto this ramp — `micro` 9px, `basis` 10px, `label` 10.5px, `meta` 11.5px, `control` 12px, `body` 13px, `numeric` 13.5px, `reading` 17px, `title` 18px, `display` 19px.
- **Column heads are two-part.** A small-caps label (10.5px / 700 / `0.09em`) over a basis line (10px / 500) naming the unit and comparison basis — `BDT / unit`, `BDT · vs cost`, `BDT · engine output`. A percentage should never need a tooltip to be legible.
- **Contrast floor is enforced, not assumed.** Measured at build: basis lines 5.6:1, size markers 6.07:1, brand labels 9.8:1, column labels 9.08:1, chips 6.29:1, hints 6.07:1. All clear 4.5:1.

## Layout

Full-bleed. The matrix runs edge to edge with no container, no max-width, and no card around it — the data is the page.

- **Two ruled header tiers, 46px each.** *Register* carries identity, counts, the sourcing books as docked tabs, the out-of-spec flag, and the write actions. *Instrument* carries search, the filters, sort, and the compare cord. Each control owns its left rule, so no boundary is ever drawn twice, and both tiers close on the same right edge.
- **Five pinned columns**, sized by custom properties (`--col-product` 300px, `--col-brand` 128px, `--col-mfg` 124px, `--col-market` 196px, `--col-selling` 210px). Each column's `left` offset is derived from those tokens rather than hard-coded, so a width change cannot desynchronise the stack.
- **Rows are 54px** with a two-line title clamp; channel columns hold a 186px minimum.
- **Adaptation is structural, never fluid.** At ≤1180px the instrument tier wraps and search goes full-width. At ≤980px the pinned columns unpin — but the header *row* stays pinned, or it tears in half on vertical scroll — and the register strip becomes stacked 44px rows. At ≤640px filters become a two-column grid; a 38px select is a control nobody can read. Type sizes never change.
- **Touch targets hold at 44px** wherever the layout goes narrow.

## Elevation & Depth

**The system is flat by default.** Depth is not decoration here, and it appears in exactly two places:

1. **The datum rule** — the pinned columns close against a 1px `rule-datum` border plus `--shadow-datum` (`6px 0 14px -8px`). It is the sheet's one structural statement: everything left of it is what we know, everything right of it is what the market is doing. Softened from full graphite — at ink weight it read as a bar drawn across the sheet rather than a boundary.
2. **Dialogs** — `--shadow-dialog` lifts a record off the sheet, with a `rgba(28, 32, 36, 0.42)` scrim behind it.

Everywhere else, layering is tonal: `sheet` over `sheet-alt` over `sheet-sunk`. Elevation is declared once — a border *or* a shadow, never a hairline border under a wide soft shadow.

## Shapes

**0px radius, without exception.** Not a stylistic tic — a ruled sheet has square cells, and a rounded one would be a card wearing a table's clothes. This holds for buttons, inputs, chips, dialogs, banners, and every count marker.

- Borders are hairlines: 1px throughout, at three weights of gray.
- **No colored side-borders above 1px.** A thick accent stripe on the edge of a callout is the most recognizable tell of generated UI; weight comes from a full field instead.
- Icons are drawn SVG at one stroke weight (1.6, round caps and joins), in `src/components/icons.tsx` for JSX and `src/client/icons.ts` for innerHTML strings. No unicode glyph ever stands in for an icon.

## Components

- **Buttons.** Primary is solid `assay-900`, full-height in the register tier. Ghost is a hairline box on sheet white. Danger is a crimson outline that fills on hover. No button is ever a pill.
- **Selects and inputs.** 30–34px, hairline border, a drawn chevron. Focus is a green border plus a 2px inset underline — the caret's own ruled line, not a glow.
- **Chips.** 2×6px padding, hairline border, a drawn arrow, tabular figures. Chips report measurements and never act as buttons.
- **Register tabs.** The two sourcing books dock into the header rule. Active carries a 2px assay-green underline seated on the boundary. Each tab's count is `aria-hidden` with the real sentence in an `aria-label` — an inline count abutting its label announces as `"Local407"`.
- **The out-of-spec flag is a button, not a readout.** It names its action (`Show 51 above market` → `Showing`) and filters the sheet on click. It counts across the whole book, never the current view: filtering to one brand must not make a catalog-wide pricing failure look like it went away.
- **The compare cord.** One control that re-reads every chip in the field at once, switching the whole sheet between markup-over-cost and discount-off-MRP.
- **Records** (product dialogs) are ruled bands, not stacked cards: an identity strip, four assay readings, a cost stack drawn to scale, a spread rail placing our price against the channels, and the channel audit. Each percentage names its basis (`VS COST`, `VS MRP`).
- **The workbook row is the leftmost column.** Every figure in the sheet is read from a cell in `Roopelle.com Final Excel Sheet.xlsx`, so the 1-based Excel row pins ahead of the product title with the sheet name beneath it — type the number into Excel's Name Box and land on the row that produced the prices. It sorts by sheet first and row second, because all five sheets start at row 2 and a bare numeric sort would interleave them. Tabular figures, like every other number.
- **Inline raw-price editing is a cell state, not a form row.** Admins click Source Cost or MRP in place; the input fills the existing cell box so a 407-row sheet never reflows. Enter commits, Escape cancels, and a local SKU floats its implied trade discount beneath the cell while typing. The violet `EDITED` marker reports a current deviation from the workbook baseline and disappears after a revert; the append-only audit history remains.
- **The `EDITED` marker is also the undo control, and it is tracked per field.** For an admin it is a button: violet at rest, crimson on hover and focus, where its label swaps to `Undo` with a drawn icon — the destructive reading is stated before the click, not after. Both faces occupy the same grid cell so the swap cannot change the chip's width and reflow the column under the pointer. Clicking restores that field's workbook figure, so reverting never requires knowing the original number. Source Cost and MRP each carry their own marker: editing one must never mark the other, or the sheet offers to revert a figure that already equals the workbook. Read-only visitors see the same marker as a plain, inert pill.
- **Admin Excel export is icon-only.** It downloads one `.xlsx` containing `Local` and `Imported` worksheets, with numeric price cells, frozen headers, filters, current engine output, workbook baselines, provenance, and every marketplace channel. It is hidden until login and requires the same-origin admin header.
- **Every interactive element ships default, hover, focus-visible, active, and disabled.** Read-only state is real: without an admin session, inputs stay readable but disabled and raw-price cells are not interactive.
- **Motion is 120–150ms and reports state only.** No page-load choreography — the app loads into a task. `prefers-reduced-motion` collapses everything to 0.001ms.
- **Browser surfaces are themed**, because they carry the design too: selection is assay green on white, scrollbars are 11px `rule-3` on `sheet-alt`, and focus rings are 2px `assay-700` at `1px` offset.

## Do's and Don'ts

**Do**
- Reach for a rule before a container. If a group needs separation, draw a hairline.
- Set every number in tabular lining figures, including inside inputs and chips.
- Name the basis of every percentage in the head's basis line or beside the reading.
- Derive chips from the *displayed* (rounded) price, so a chip always describes the number on screen.
- Keep absence honest — a missing listing is a quiet dash on a recessed ground, never a fabricated price, placeholder image, or invented link.
- Give any numeral sitting beside a word an `aria-hidden` wrapper and put the real sentence in `aria-label`.

**Don't**
- Don't introduce a radius. Not on a chip, not on a modal, not "just a small one."
- Don't add a third semantic color. Green is healthy, crimson has failed; violet is spoken for by operator-set values (tuning and raw price edits).
- Don't put a colored border above 1px on the side of anything.
- Don't nest cards, or use a card where a ruled band works.
- Don't use `ink-4` for text — it is for marks and dashes only.
- Don't let type reflow fluidly across breakpoints; adapt the structure instead.
- Don't render an unsellable recommendation as though it were valid.
- Don't substitute a unicode glyph for a drawn icon.
