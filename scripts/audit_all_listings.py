"""Audit every verified marketplace listing in the local D1 replica.

Three independent checks per listing:

1. **Reachability** — the URL resolves (HTTP 2xx) and does not 404.
2. **Identity** — the final URL after redirects still points at the same
   product. A redirect that lands on a different slug means the ID in our
   link is not the ID of the product we matched (the Arogga ``pv_id`` bug).
3. **Integrity** — ``sku_matcher.validate_match`` still accepts the stored
   ``matched_title`` against the catalog SKU, so a tightened matcher
   retroactively flags listings accepted under looser rules.

Writes a JSON report to ``/tmp/listing_audit.json`` and prints a summary.
"""
from __future__ import annotations

import concurrent.futures
import json
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sku_matcher import validate_match  # noqa: E402

D1_DIR = ROOT / ".wrangler/state/v3/d1/miniflare-D1DatabaseObject"
REPORT_PATH = Path("/tmp/listing_audit.json")

RETRIES = 3
TIMEOUT_S = 40

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    )
}

# Words that should never appear in a beauty/personal-care product URL.
# These are the pharmacy/grocery aisles an Arogga mis-ID lands you in.
OFF_CATALOG = [
    "tablet", "capsule", "syrup", "injection", "tonic", "suspension",
    "infusion", "ointment", "pharma", "medicine", "scalp-vein", "needle",
    "syringe", "antibiotic", "paracetamol", "insulin", "inhaler",
]


def db_path() -> Path:
    candidates = [p for p in D1_DIR.glob("*.sqlite") if "metadata" not in p.name]
    if not candidates:
        raise SystemExit(f"No D1 replica found under {D1_DIR}")
    return max(candidates, key=lambda p: p.stat().st_size)


def slug_of(url: str) -> str:
    return url.rstrip("/").split("/")[-1].lower()


def product_id_of(url: str) -> str | None:
    """The numeric product ID in a marketplace URL, when it has one.

    Arogga and Rokomari key on /product/<id>/<slug>. The ID is the real
    identity; the slug is decoration a site may rewrite between requests
    (Rokomari alternates '1pcs' and '1pc'). Same ID means same product.
    """
    match = re.search(r"/product/(\d+)(?:/|$)", url)
    return match.group(1) if match else None


def check(row: sqlite3.Row) -> dict | None:
    row_id = row["row_id"]
    channel = row["channel_name"]
    url = row["url"]

    base = {
        "row_id": row_id,
        "channel": channel,
        "product_name": row["product_name"],
        "matched_title": row["matched_title"],
        "url": url,
    }

    # --- Check 3: match integrity (offline, always runs) ---
    # Mirror catalog_builder.validate_listing exactly: the brand often lives in
    # the seller or domain rather than the title (a brand's own store does not
    # repeat its name), so seller + URL are part of the candidate context.
    result = validate_match(
        brand=row["brand_name"],
        product_name=row["product_name"],
        target_size_text=row["size_text"],
        candidate_name=row["matched_title"] or "",
        candidate_context=" ".join(
            str(v or "") for v in (row["seller"], row["url"])
        ),
        candidate_size_text=row["listing_size"],
    )
    if not result.accepted:
        return {**base, "kind": "match", "detail": "; ".join(result.reasons)}

    # --- Checks 1 & 2: reachability + identity (network) ---
    # Slow origins (neofarmers, Arogga under load) time out on a first pass and
    # then answer fine. Retry before calling a listing broken, or the report
    # buries four real 404s under seventeen phantoms.
    final = None
    last_error = ""
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                final = resp.geturl()
            break
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429):
                return None  # bot wall, not a data defect
            return {**base, "kind": "http", "detail": f"HTTP {exc.code}"}
        except Exception as exc:  # noqa: BLE001 - network is best-effort
            last_error = str(exc)
            if attempt < RETRIES - 1:
                time.sleep(2 * (attempt + 1))

    if final is None:
        return {**base, "kind": "network", "detail": last_error}

    final_slug = slug_of(final)
    for kw in OFF_CATALOG:
        if re.search(rf"\b{re.escape(kw)}\b", final_slug.replace("-", " ")):
            return {**base, "kind": "off_catalog",
                    "detail": f"landed on '{final_slug}' ({kw})"}

    if slug_of(url) != final_slug:
        # A same-ID redirect is the site normalising its own slug, not a
        # different product. Only flag when the identity actually changes.
        original_id = product_id_of(url)
        if original_id is not None and original_id == product_id_of(final):
            return None
        return {**base, "kind": "redirect",
                "detail": f"{slug_of(url)} -> {final_slug}"}

    return None


def main() -> int:
    con = sqlite3.connect(db_path())
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT ml.row_id, ml.channel_name, ml.url, ml.matched_title,
               ml.size AS listing_size, ml.seller,
               p.product_name, p.brand_name, p.size AS size_text, p.sourcing_origin
        FROM marketplace_listings ml
        JOIN products p ON p.row_id = ml.row_id
        WHERE ml.verified = 1 AND ml.url IS NOT NULL AND ml.url <> ''
        ORDER BY ml.channel_name, ml.row_id
        """
    ).fetchall()

    print(f"Auditing {len(rows)} verified listings across all channels...")

    findings: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for result in pool.map(check, rows):
            if result:
                findings.append(result)

    by_channel: dict[str, int] = {}
    for r in rows:
        by_channel[r["channel_name"]] = by_channel.get(r["channel_name"], 0) + 1

    flagged_by_channel: dict[str, int] = {}
    flagged_by_kind: dict[str, int] = {}
    for f in findings:
        flagged_by_channel[f["channel"]] = flagged_by_channel.get(f["channel"], 0) + 1
        flagged_by_kind[f["kind"]] = flagged_by_kind.get(f["kind"], 0) + 1

    print("\nPer-channel coverage (verified listings / flagged):")
    for ch in sorted(by_channel):
        print(f"  {ch:16s} {by_channel[ch]:4d} checked, {flagged_by_channel.get(ch, 0):3d} flagged")

    print(f"\nTotal findings: {len(findings)}")
    for kind, count in sorted(flagged_by_kind.items()):
        print(f"  {kind:12s} {count}")

    REPORT_PATH.write_text(json.dumps(findings, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
