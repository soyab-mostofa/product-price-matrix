"""Repair listings that the audit proved dead, in the canonical research file.

``verified_marketplace_research.json`` is the source the whole pipeline is
rebuilt from, so a dead link must be fixed *here* — patching D1 directly gets
overwritten by the next ``build_matrix.py`` run.

Two kinds of repair, both driven by findings from
``scripts/audit_all_listings.py``:

* **relink** — the product still exists at a new URL (Shajgoj rewrites slugs
  when a batch's expiry date changes). Replace url/price/title in place.
* **drop** — the SKU is genuinely delisted at that size (Arogga now stocks
  only the 250ml of a 130ml SKU). Remove the channel rather than keep a 404
  or silently point at the wrong size.

Every repair is verified live before it is written.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RESEARCH_PATH = ROOT / "verified_marketplace_research.json"

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    )
}

# --- Findings from scripts/audit_all_listings.py -------------------------
# Shajgoj slugs carry the batch expiry date; when the batch rolls over the old
# slug 404s. Both of these re-resolved to a live listing under the same SKU.
RELINK: dict[tuple[int, str], dict] = {
    (256, "Shajgoj"): {
        "price": 255,
        "url": "https://shop.shajgoj.com/product/skin-cafe-end-of-dull-hair-banana-shampoo-with-egg-protein-expiry-date-october-2026",
        "matched_title": "Skin Cafe End of Dull Hair Banana Shampoo with Egg Protein (Expiry date - October 2026)",
    },
    (292, "Shajgoj"): {
        "price": 213,
        "url": "https://shop.shajgoj.com/product/hawaa-hair-fall-avenger-oil-2-2-2-YDj",
        "matched_title": "Hawaa Hair Fall Avenger Oil",
    },
}

# Arogga delisted the 130ml jars; only a 250ml SKU remains, which is a
# different product at a different price. Keeping the link would 404 and
# swapping in the 250ml would corrupt the size-matched benchmark.
DROP: set[tuple[int, str]] = {
    (142, "Arogga"),
    (143, "Arogga"),
}


def reachable(url: str) -> bool:
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        return exc.code in (403, 429)  # bot wall, page exists
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    data = json.loads(RESEARCH_PATH.read_text(encoding="utf-8"))

    # Verify every replacement URL is live before touching the file.
    for (row_id, channel), patch in RELINK.items():
        if not reachable(patch["url"]):
            print(f"ABORT: replacement for [{row_id}] {channel} is not reachable:\n  {patch['url']}")
            return 1
        print(f"verified live: [{row_id}] {channel} -> {patch['url']}")

    relinked = dropped = 0
    for product in data["products"]:
        row_id = product.get("row")
        sources = product.get("sources") or {}

        for channel in list(sources):
            key = (row_id, channel)

            if key in DROP:
                del sources[channel]
                dropped += 1
                print(f"dropped  [{row_id}] {channel} — SKU delisted at this size")
                continue

            patch = RELINK.get(key)
            if patch:
                listing = sources[channel]
                listing["price"] = patch["price"]
                listing["url"] = patch["url"]
                listing["matched_title"] = patch["matched_title"]
                relinked += 1
                print(f"relinked [{row_id}] {channel} — {patch['price']}")

    RESEARCH_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\n{relinked} relinked, {dropped} dropped -> {RESEARCH_PATH.name}")
    print("Now run: uv run --with openpyxl --with rapidfuzz python3 build_matrix.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
