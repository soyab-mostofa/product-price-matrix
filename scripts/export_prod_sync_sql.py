"""Export full local D1 database state (local + imported products and listings)
into chunked SQL statements suitable for remote D1 execution.
"""

from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
D1_DIR = ROOT / ".wrangler/state/v3/d1/miniflare-D1DatabaseObject"
OUT_FILE = ROOT / "/tmp/sync_remote_d1.sql"

def get_local_db() -> Path:
    for p in sorted(D1_DIR.glob("*.sqlite")):
        if p.name != "metadata.sqlite":
            return p
    raise RuntimeError("No local SQLite db found")

def sql_quote(val):
    if val is None:
        return "NULL"
    if isinstance(val, (int, float)):
        return str(val)
    escaped = str(val).replace("'", "''")
    return f"'{escaped}'"

def main():
    db_path = get_local_db()
    con = sqlite3.connect(db_path)
    
    lines = []
    lines.append("-- Sync global pricing params")
    gp = con.execute("SELECT id, packaging, transport, delivery, cac, target_margin_pct, discount_type, discount_val FROM global_pricing_params WHERE id = 1").fetchone()
    if gp:
        lines.append(f"INSERT INTO global_pricing_params (id, packaging, transport, delivery, cac, target_margin_pct, discount_type, discount_val) VALUES ({gp[0]}, {gp[1]}, {gp[2]}, {gp[3]}, {gp[4]}, {gp[5]}, {sql_quote(gp[6])}, {gp[7]}) ON CONFLICT(id) DO UPDATE SET packaging=excluded.packaging, transport=excluded.transport, delivery=excluded.delivery, cac=excluded.cac, target_margin_pct=excluded.target_margin_pct, discount_type=excluded.discount_type, discount_val=excluded.discount_val;")

    lines.append("\n-- Sync products (596 SKUs: 407 local + 189 imported)")
    products = con.execute("SELECT row_id, product_name, brand_name, size, manufactured_price, market_average_price, canonical_name, mrp_source_type, sourcing_origin, category FROM products ORDER BY row_id ASC").fetchall()
    for p in products:
        lines.append(
            f"INSERT INTO products (row_id, product_name, brand_name, size, manufactured_price, market_average_price, canonical_name, mrp_source_type, sourcing_origin, category) "
            f"VALUES ({p[0]}, {sql_quote(p[1])}, {sql_quote(p[2])}, {sql_quote(p[3])}, {p[4]}, {p[5]}, {sql_quote(p[6])}, {sql_quote(p[7])}, {sql_quote(p[8])}, {sql_quote(p[9])}) "
            f"ON CONFLICT(row_id) DO UPDATE SET product_name=excluded.product_name, brand_name=excluded.brand_name, size=excluded.size, manufactured_price=excluded.manufactured_price, market_average_price=excluded.market_average_price, canonical_name=excluded.canonical_name, mrp_source_type=excluded.mrp_source_type, sourcing_origin=excluded.sourcing_origin, category=excluded.category;"
        )

    lines.append("\n-- Sync marketplace listings (1,334 listings)")
    listings = con.execute("SELECT row_id, channel_name, price, url, matched_title, size, seller, confidence, available, verified FROM marketplace_listings ORDER BY row_id ASC, channel_name ASC").fetchall()
    for l in listings:
        lines.append(
            f"INSERT INTO marketplace_listings (row_id, channel_name, price, url, matched_title, size, seller, confidence, available, verified) "
            f"VALUES ({l[0]}, {sql_quote(l[1])}, {l[2]}, {sql_quote(l[3])}, {sql_quote(l[4])}, {sql_quote(l[5])}, {sql_quote(l[6])}, {l[7]}, {l[8]}, {l[9]}) "
            f"ON CONFLICT(row_id, channel_name) DO UPDATE SET price=excluded.price, url=excluded.url, matched_title=excluded.matched_title, size=excluded.size, seller=excluded.seller, confidence=excluded.confidence, available=excluded.available, verified=excluded.verified;"
        )

    OUT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {len(products)} products and {len(listings)} listings to {OUT_FILE}")

if __name__ == "__main__":
    main()
