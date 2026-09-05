"""Purge listings the hardened matcher now rejects, and restore lost sizes.

Two classes of defect, both surfaced by ``scripts/audit_all_listings.py``:

* **Rival sub-line** — the listing is a different product whose title differs
  by one word (Streax *Vitalized* vs *Shine*). These are deleted: pointing a
  shopper at the wrong bottle is worse than showing no price.
* **Dropped size** — the match was validated against a candidate size that
  ``record_match`` then discarded, so a re-audit could not reproduce the
  verdict. These are re-validated against the live channel and their size is
  written back; only listings that still pass are kept.

Run after the scrapers, before rebuilding artifacts.
"""
from __future__ import annotations

import glob
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from sku_matcher import validate_match  # noqa: E402
from scrape_imported import CHANNELS  # noqa: E402

D1_DIR = ROOT / ".wrangler/state/v3/d1/miniflare-D1DatabaseObject"


def replicas() -> list[Path]:
    return [
        Path(p) for p in sorted(glob.glob(str(D1_DIR / "*.sqlite")))
        if "metadata" not in os.path.basename(p)
    ]


def main() -> int:
    paths = replicas()
    if not paths:
        raise SystemExit(f"No D1 replica under {D1_DIR}")

    primary = sqlite3.connect(max(paths, key=lambda p: p.stat().st_size))
    primary.row_factory = sqlite3.Row

    rows = primary.execute(
        """
        SELECT ml.row_id, ml.channel_name, ml.matched_title, ml.size AS listing_size,
               ml.url, ml.seller,
               p.product_name, p.brand_name, p.size AS target_size
        FROM marketplace_listings ml
        JOIN products p ON p.row_id = ml.row_id
        WHERE ml.verified = 1
        ORDER BY ml.row_id
        """
    ).fetchall()

    channels: dict[str, object] = {}
    for name, cls in CHANNELS.items():
        try:
            channels[name] = cls()
        except Exception as exc:  # noqa: BLE001
            print(f"channel {name} unavailable: {exc}")

    to_delete: list[tuple[int, str]] = []
    to_resize: list[tuple[int, str, str]] = []

    for row in rows:
        verdict = validate_match(
            brand=row["brand_name"],
            product_name=row["product_name"],
            target_size_text=row["target_size"],
            candidate_name=row["matched_title"] or "",
            candidate_context=" ".join(str(v or "") for v in (row["seller"], row["url"])),
            candidate_size_text=row["listing_size"],
        )
        if verdict.accepted:
            continue

        reasons = "; ".join(verdict.reasons)

        # A rival sub-line is a different product — never repairable.
        if "sub-line mismatch" in reasons or "missing sub-line" in reasons:
            to_delete.append((row["row_id"], row["channel_name"]))
            print(f"DELETE [{row['row_id']}] {row['channel_name']}: {reasons[:70]}")
            continue

        # Only the size is missing: recover it from the live channel and
        # re-validate. If it still fails, the listing goes.
        if "candidate size missing" in reasons:
            channel = channels.get(row["channel_name"])
            recovered = None
            if channel is not None:
                try:
                    for hit in channel.search(row["product_name"])[:10]:  # type: ignore[attr-defined]
                        parsed = channel.extract(hit)  # type: ignore[attr-defined]
                        if not parsed:
                            continue
                        title, _price, url, size = parsed
                        if url == row["url"] and size:
                            recovered = size
                            break
                except Exception:  # noqa: BLE001
                    recovered = None

            if recovered:
                recheck = validate_match(
                    brand=row["brand_name"],
                    product_name=row["product_name"],
                    target_size_text=row["target_size"],
                    candidate_name=row["matched_title"] or "",
                    candidate_context=" ".join(str(v or "") for v in (row["seller"], row["url"])),
                    candidate_size_text=recovered,
                )
                if recheck.accepted:
                    to_resize.append((row["row_id"], row["channel_name"], recovered))
                    print(f"RESIZE [{row['row_id']}] {row['channel_name']}: size={recovered}")
                    continue

            to_delete.append((row["row_id"], row["channel_name"]))
            print(f"DELETE [{row['row_id']}] {row['channel_name']}: {reasons[:70]}")
            continue

        to_delete.append((row["row_id"], row["channel_name"]))
        print(f"DELETE [{row['row_id']}] {row['channel_name']}: {reasons[:70]}")

    primary.close()

    for path in paths:
        con = sqlite3.connect(path, timeout=30)
        con.execute("PRAGMA busy_timeout = 30000")
        for row_id, channel in to_delete:
            con.execute(
                "DELETE FROM marketplace_listings WHERE row_id = ? AND channel_name = ?",
                (row_id, channel),
            )
        for row_id, channel, size in to_resize:
            con.execute(
                "UPDATE marketplace_listings SET size = ? WHERE row_id = ? AND channel_name = ?",
                (size, row_id, channel),
            )
        con.commit()
        con.close()

    print(f"\n{len(to_delete)} deleted, {len(to_resize)} resized across {len(paths)} replica(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
