# Product Price Intelligence & Marketplace Benchmark Matrix

Price benchmark dataset and dashboard for personal care and beauty SKUs, comparing what we pay to acquire a product against what it sells for across Bangladeshi e-commerce channels.

## Language

### Sourcing provenance

**Sourcing Origin**:
The axis describing how a SKU reaches us. Exactly two values: `local` and `imported`.
_Avoid_: source type, product type, origin country

**Local SKU**:
A product manufactured in Bangladesh and sourced direct from its manufacturer, at a discounted manufacturer price.
_Avoid_: domestic, native, local product

**Imported SKU**:
A product brought into the country and sourced from an importer. Its cost basis is the importer's quoted price — there is no manufacturer discount to apply.
_Avoid_: foreign, overseas, imported product

**Source Cost**:
What we pay to acquire one unit, whatever the Sourcing Origin. For a Local SKU this is the discounted manufacturer price; for an Imported SKU it is the importer's quoted price. Stored in the `manufactured_price` column for historical reasons.
_Avoid_: MFG price, cost price, buy price, manufactured price

**Seeding**:
Loading rows into the database from a source workbook or sheet. Deliberately not called "importing" — that word is reserved for Sourcing Origin.
_Avoid_: importing, data import, ingest

### Pricing

**MRP**:
The reference market price for a SKU: the Official Store price when one exists, otherwise the mean of active third-party listings, otherwise the workbook benchmark. Which of the three applied is recorded as the MRP source type.
_Avoid_: market price, retail price, list price

**Selling Price**:
The price the Pricing Engine recommends we sell at, derived from Source Cost plus overheads, target margin, and any discount.
_Avoid_: sale price, our price, final price

**Pricing Engine**:
The calculation turning Source Cost into a Selling Price via packaging, transport, delivery, CAC, target margin, and a discount. It is origin-agnostic — it reads Source Cost and does not care whether a SKU is local or imported.
_Avoid_: calculator, price model

**Tune**:
A sparse per-SKU override of Pricing Engine parameters. Every field is optional; an absent field inherits the current global value, so global cost changes still reach tuned SKUs.
_Avoid_: override, custom pricing, per-product config

**Markup %**:
A channel or selling price expressed as its percentage difference from Source Cost.
_Avoid_: margin, uplift, profit

### Marketplace data

**Channel**:
A storefront where a SKU is listed and priced — either the brand's Official Store or a third-party marketplace (Arogga, Shajgoj, OhSoGo, Daraz, eMartWay, PandaMart, Rokomari).
_Avoid_: marketplace, source, vendor, retailer

**Listing**:
One SKU's live presence on one Channel: its active checkout price plus a deep link to the product page. A SKU has at most one Listing per Channel.
_Avoid_: match, offer, result

**Official Store**:
The brand's own flagship storefront, treated as authoritative for MRP and ranked above third-party Channels.
_Avoid_: brand store, first-party, direct
