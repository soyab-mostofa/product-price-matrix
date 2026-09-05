"""Fold D1-discovered listings back into the canonical research file.

The scrapers write straight into the D1 replicas, but
``verified_marketplace_research.json`` is what ``build_matrix.py`` rebuilds
from — so a discovery run that is not folded back is silently undone by the
next rebuild.

Only **local** SKUs are folded: the imported book is seeded from the workbook
by ``scripts/seed_imported.py`` and does not live in the research file.

Every listing is re-validated against ``sku_matcher`` before it is written, so
this can never introduce a match the audit would reject. Existing entries are
updated in place (price, url, title, size); new channels are added.
"""
from __future__ import annotations

import glob
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sku_matcher import validate_match  # noqa: E402

RESEARCH = ROOT / "verified_marketplace_research.json"
D1_DIR = ROOT / ".wrangler/state/v3/d1/miniflare-D1DatabaseObject"


def replica() -> Path:
    paths = [
        Path(p) for p in glob.glob(str(D1_DIR / "*.sqlite"))
        if "metadata" not in os.path.basename(p)
    ]
    if not paths:
        raise SystemExit(f"No D1 replica under {D1_DIR}")
    return max(paths, key=lambda p: p.stat().st_size)


def main() -> int:
    con = sqlite3.connect(replica())
    con.row_factory = sqlite3.Row
    listings = con.execute(
        """
        SELECT ml.row_id, ml.channel_name, ml.price, ml.url, ml.matched_title,
               ml.size AS listing_size, ml.seller, ml.confidence,
               p.product_name, p.brand_name, p.size AS target_size
        FROM marketplace_listings ml
        JOIN products p ON p.row_id = ml.row_id
        WHERE p.sourcing_origin = 'local' AND ml.verified = 1
          AND ml.url IS NOT NULL AND ml.url <> ''
        """
    ).fetchall()
    con.close()

    by_row: dict[int, dict[str, sqlite3.Row]] = {}
    for row in listings:
        by_row.setdefault(row["row_id"], {})[row["channel_name"]] = row

    research = json.loads(RESEARCH.read_text(encoding="utf-8"))

    added = updated = skipped = 0
    for product in research["products"]:
        found = by_row.get(int(product["row"]))
        if not found:
            continue
        sources = product.setdefault("sources", {})

        for channel, row in found.items():
            verdict = validate_match(
                brand=row["brand_name"],
                product_name=row["product_name"],
                target_size_text=row["target_size"],
                candidate_name=row["matched_title"] or "",
                candidate_context=" ".join(str(v or "") for v in (row["seller"], row["url"])),
                candidate_size_text=row["listing_size"],
            )
            if not verdict.accepted:
                skipped += 1
                continue

            entry = sources.get(channel)
            payload = {
                "price": row["price"],
                "url": row["url"],
                "matched_title": row["matched_title"],
                "size": row["listing_size"],
                "seller": row["seller"],
                "available": True,
                "confidence": float(row["confidence"] or 100.0),
            }
            if entry is None:
                sources[channel] = payload
                added += 1
            elif (entry.get("url") != payload["url"]
                  or entry.get("price") != payload["price"]
                  or entry.get("size") != payload["size"]):
                entry.update(payload)
                updated += 1

    RESEARCH.write_text(
        json.dumps(research, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{added} listings added, {updated} updated, {skipped} skipped (failed revalidation)")
    print(f"-> {RESEARCH.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
