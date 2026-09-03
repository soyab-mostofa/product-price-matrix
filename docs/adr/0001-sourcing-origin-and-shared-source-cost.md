# Sourcing origin is an axis on one product table, over one shared source cost

The catalog now covers products acquired two ways — Local SKUs bought from Bangladeshi manufacturers at a discounted manufacturer price, and Imported SKUs bought from importers at the importer's quoted price. We model this as a `sourcing_origin` column (`local` | `imported`) on the existing `products` table, backfilled to `local` for all 407 existing rows, rather than as a second table or a second cost column.

The Pricing Engine stays origin-agnostic: it reads one cost column — the domain's **Source Cost** — and applies the same overhead, margin, and discount arithmetic regardless of origin.

## Considered Options

- **A separate `importer_price` column, engine selects by origin.** Rejected: it forks every pricing code path on a boolean, doubles the null-handling, and buys nothing while the arithmetic is identical on both sides.
- **A separate `imported_products` table.** Rejected: the two sides share every column, every index, and the entire listings/overrides foreign-key graph. Splitting them would duplicate the schema to express one flag.
- **Adding duty/freight/landed-cost knobs to the engine now.** Deferred deliberately. The confirmed rule today is that an Imported SKU's cost basis *is* the importer's quoted price, with no manufacturer discount to apply and no landed cost riding on top. Adding unused knobs would be speculative.

## Consequences

The physical column keeps its historical name `manufactured_price` while the domain calls it Source Cost, so for an Imported SKU the column name is a mild lie — `CONTEXT.md` carries the correction. A rename is a wide, mechanical migration we can take later without changing behaviour.

Because origin is a filter rather than a structural split, the same product legitimately sourced both ways is two rows with two Source Costs and two margins — that comparison is the point, not a duplication bug. Seeding reports name/size overlaps for human review instead of auto-merging.

If landed cost later becomes real, it is a new engine field applied to imported rows — not a fork of the cost input.
