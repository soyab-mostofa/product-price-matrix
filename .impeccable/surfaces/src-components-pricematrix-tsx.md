---
version: 1
slug: "src-components-pricematrix-tsx"
primary_target: "src/components/PriceMatrix.tsx"
related_targets: ["src/components/Header.tsx","src/components/Modals.tsx","src/components/OriginSwitch.tsx","public/static/app.css"]
---

## Direction contract

THESIS: A price recommendation is an assay result, not a dashboard tile. Every SKU is a specimen with a measured value (recommended selling price), a specification limit (MRP benchmark), and replicate measurements (channel listings) — read as one ruled sheet. Refuses the card-grid admin dashboard and the tile-of-KPIs header.

OWN-WORLD: Lab-report paper (warm white `#FBFBF9`, sheet white), graphite hairline rules at 0px radius everywhere, no cards and no elevation except the pinned datum line. One committed assay green `#0F6B4F` for brand, action, and in-spec; out-of-spec crimson `#9F1C1C`. The markup chip is an ordered measurement ramp, not six unrelated pastels. Inter set in lining tabular figures throughout; column heads are small-caps labels over a faint unit-of-measure line.

STORY: The operator scans the sheet, sees which specimens sit outside spec, understands why from the basis line under each column head, and opens one specimen record to correct it.

FIRST VIEWPORT: Two-tier ruled sheet header — wordmark and live-sync dot left, the two sourcing books docked as ruled register tabs carrying their counts, coverage readout and an out-of-spec count that filters the sheet on click, right. Second tier: search, brand, channel, category, sort, and the compare cord. Below it the matrix runs full-bleed edge to edge, five pinned specimen columns closed by a 1px graphite datum rule, replicate channel columns running right.

FORM: Certificate-of-analysis assay sheet; candidate 5 of the grounded list; seed key f4a866eb.

RAISE (from ikeda-datamatics, declined): density courage — the matrix is full-bleed, no container chrome; the data is the page.
RAISE (from teletext, declined): the sacred row — fixed column widths and tabular lining figures so digits and chips align down every column.
RAISE (from labanotation, competitive): fill is measurement — the chip ramp reads as an ordered scale, never decoration.
RAISE (from drawcord cape, declined): one cord — a single control re-reads every chip in the field at once.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
