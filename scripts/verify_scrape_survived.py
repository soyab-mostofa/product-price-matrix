"""Confirm every listing the scraper reported still exists downstream.

A discovery pass writes into the D1 replicas, but `db:local:sync` rebuilds the
local book from `verified_marketplace_research.json`. If a run is not folded
back before that sync, its findings are silently reverted — the scraper's
success log is not evidence the data survived.

Parses scripts/scrape_missing.py's log, then checks each reported
(product, channel) pair in the research file, the local D1 replica, and the
live production API.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sqlite3
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = Path("/tmp/scrape_missing.log")
RESEARCH = ROOT / "verified_marketplace_research.json"
D1_DIR = ROOT / ".wrangler/state/v3/d1/miniflare-D1DatabaseObject"
BASE = "https://product-price-matrix.pages.dev"

UA = {"User-Agent": "Mozilla/5.0"}

# "  [12/286] [local] Shajgoj  ৳    180 (100%) -> Nirvana Color Matte Color Bullet – Berry"
LINE = re.compile(
    r"^\s*\[\d+/\d+\]\s+\[(?P<origin>local|imported)\]\s+(?P<channel>\S+)\s+"
    r"৳\s*(?P<price>[\d.]+)\s+\((?P<conf>[\d.]+)%\)\s*->\s*(?P<name>.+?)\s*$"
)


def key_of(name: str, channel: str) -> tuple[str, str]:
    """Match on the log's truncated, right-stripped name.

    The scraper prints `name[:40]`, and a name whose 40th character is a space
    loses it in the log — so compare on the stripped prefix, or correct
    listings read as missing.
    """
    return (name[:40].strip(), channel)


def replica() -> Path:
    paths = [Path(p) for p in glob.glob(str(D1_DIR / "*.sqlite"))
             if "metadata" not in os.path.basename(p)]
    if not paths:
        raise SystemExit("no D1 replica")
    return max(paths, key=lambda p: p.stat().st_size)


def main() -> int:
    if not LOG.exists():
        raise SystemExit(f"no scraper log at {LOG}")

    reported: list[tuple[str, str, str]] = []
    for line in LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        m = LINE.match(line)
        if m:
            reported.append((m["origin"], m["channel"], m["name"]))

    print(f"scraper reported {len(reported)} matches (names truncated in the log)\n")

    # The log truncates names to 40 chars, so match on prefix.
    research = json.loads(RESEARCH.read_text(encoding="utf-8"))
    research_pairs = {
        key_of(p["product_name"], channel)
        for p in research["products"]
        for channel in (p.get("sources") or {})
    }

    con = sqlite3.connect(replica())
    db_pairs = {
        key_of(name, channel)
        for name, channel in con.execute(
            "SELECT p.product_name, ml.channel_name FROM marketplace_listings ml "
            "JOIN products p ON p.row_id = ml.row_id WHERE ml.verified = 1"
        )
    }
    con.close()

    live_pairs: set[tuple[str, str]] = set()
    for origin in ("local", "imported"):
        req = urllib.request.Request(f"{BASE}/api/products?origin={origin}", headers=UA)
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        for product in payload.get("products", []):
            for channel in (product.get("sources") or {}):
                live_pairs.add(key_of(product.get("product_name", ""), channel))

    missing_research: list[tuple[str, str, str]] = []
    missing_db: list[tuple[str, str, str]] = []
    missing_live: list[tuple[str, str, str]] = []

    for origin, channel, name in reported:
        key = key_of(name, channel)
        # Local SKUs live in the research file; imported ones are seeded from
        # the workbook and legitimately absent from it.
        if origin == "local" and key not in research_pairs:
            missing_research.append((origin, channel, name))
        if key not in db_pairs:
            missing_db.append((origin, channel, name))
        if key not in live_pairs:
            missing_live.append((origin, channel, name))

    for label, rows in (
        ("research file (local only)", missing_research),
        ("local D1 replica", missing_db),
        ("LIVE production API", missing_live),
    ):
        status = "OK" if not rows else f"{len(rows)} MISSING"
        print(f"{label:28s} {status}")
        for origin, channel, name in rows:
            print(f"    [{origin}] {channel} — {name}")

    total = len(missing_research) + len(missing_db) + len(missing_live)
    print(f"\n{'PASS' if total == 0 else 'FAIL'} — every reported match survived to production"
          if total == 0 else f"\nFAIL — {total} reported matches did not survive")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
