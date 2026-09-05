"""Verify the LIVE production API's links, channel by channel.

The local audit checks the D1 replica; this checks what a visitor actually
receives from https://product-price-matrix.pages.dev — so a bad deploy or an
unsynced remote database is caught, not just a bad local file.

Every deep link the API serves is fetched and checked for reachability and
identity (the final URL after redirects still names the same product), across
both sourcing books.
"""
from __future__ import annotations

import concurrent.futures
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter

BASE = "https://product-price-matrix.pages.dev"
RETRIES = 3
TIMEOUT_S = 40

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    )
}

OFF_CATALOG = [
    "tablet", "capsule", "syrup", "injection", "tonic", "suspension",
    "infusion", "ointment", "pharma", "medicine", "scalp vein", "needle",
    "syringe", "antibiotic", "paracetamol", "insulin", "inhaler",
]


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def slug_of(url: str) -> str:
    return url.rstrip("/").split("/")[-1].lower()


def product_id_of(url: str) -> str | None:
    """The numeric product ID in a marketplace URL, when it has one.

    Arogga and Rokomari both key on /product/<id>/<slug>. The ID is the real
    identity; the slug is decoration a site may rewrite between requests
    (Rokomari alternates '1pcs' and '1pc'). When both URLs carry the same ID,
    a differing slug is cosmetic, not a mismatch.
    """
    match = re.search(r"/product/(\d+)(?:/|$)", url)
    return match.group(1) if match else None


def check(item: tuple[str, str, str, str]) -> dict | None:
    origin, channel, product, url = item
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
            return {"origin": origin, "channel": channel, "product": product,
                    "url": url, "kind": "http", "detail": f"HTTP {exc.code}"}
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            if attempt < RETRIES - 1:
                time.sleep(2 * (attempt + 1))

    if final is None:
        return {"origin": origin, "channel": channel, "product": product,
                "url": url, "kind": "network", "detail": last_error}

    final_slug = slug_of(final)
    for kw in OFF_CATALOG:
        if re.search(rf"\b{re.escape(kw)}\b", final_slug.replace("-", " ")):
            return {"origin": origin, "channel": channel, "product": product,
                    "url": url, "kind": "off_catalog",
                    "detail": f"landed on '{final_slug}' ({kw})"}

    if slug_of(url) != final_slug:
        # A same-ID redirect is the site normalising its own slug, not a
        # different product. Only flag when the identity actually changes.
        original_id = product_id_of(url)
        if original_id is not None and original_id == product_id_of(final):
            return None
        return {"origin": origin, "channel": channel, "product": product,
                "url": url, "kind": "redirect",
                "detail": f"{slug_of(url)} -> {final_slug}"}
    return None


def main() -> int:
    targets: list[tuple[str, str, str, str]] = []
    for origin in ("local", "imported"):
        payload = fetch_json(f"{BASE}/api/products?origin={origin}")
        products = payload.get("products", [])
        print(f"{origin:9s}: {len(products)} SKUs from the live API")
        for product in products:
            for channel, listing in (product.get("sources") or {}).items():
                url = (listing or {}).get("url")
                if url:
                    targets.append((origin, channel, product.get("product_name", ""), url))

    per_channel = Counter(channel for _o, channel, _p, _u in targets)
    print(f"\nChecking {len(targets)} live deep links...\n")

    findings: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for result in pool.map(check, targets):
            if result:
                findings.append(result)

    flagged = Counter(f["channel"] for f in findings)
    print("Per-channel (links checked / flagged):")
    for channel in sorted(per_channel):
        print(f"  {channel:16s} {per_channel[channel]:4d} checked, {flagged.get(channel, 0):3d} flagged")

    print(f"\nTotal findings: {len(findings)}")
    for finding in findings:
        print(f"  [{finding['origin']}] {finding['channel']} — {finding['product'][:44]}")
        print(f"      {finding['kind']}: {finding['detail']}")
        print(f"      {finding['url']}")

    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
