from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any

from sku_matcher import MatchResult, validate_match

ROOT = Path(__file__).resolve().parent
RESEARCH_PATH = ROOT / "verified_marketplace_research.json"
JSON_PATH = ROOT / "product_pricing_data.json"
PUBLIC_DIR = ROOT / "public"
PUBLIC_JSON_PATH = PUBLIC_DIR / "product_pricing_data.json"
AUDIT_PATH = ROOT / "verified_match_audit.json"
SEED_PATH = ROOT / "seed.sql"

CHANNEL_ORDER = [
    "Official Store",
    "Arogga",
    "Shajgoj",
    "OhSoGo",
    "Daraz",
    "eMartWay",
    "PandaMart",
    "Rokomari",
    "Chaldal",
]
CHANNEL_RANK = {channel: index for index, channel in enumerate(CHANNEL_ORDER)}

DEFAULT_GLOBAL_PARAMS = {
    "packaging": 45.0,
    "transport": 0.0,
    "delivery": 0.0,
    "cac": 40.0,
    "targetMarginPct": 0.0,
    "discountType": "pct",
    "discountVal": 0.0,
}


@dataclass
class CatalogValidationError(ValueError):
    violations: list[dict[str, Any]]

    def __str__(self) -> str:
        examples = "; ".join(
            f"row {item['row']} {item['channel']}: {', '.join(item['reasons'])}"
            for item in self.violations[:5]
        )
        suffix = "" if len(self.violations) <= 5 else f"; +{len(self.violations) - 5} more"
        return f"{len(self.violations)} active listing validation error(s): {examples}{suffix}"


def _number(value: Any, *, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    if result < 0:
        raise ValueError(f"{field} must be non-negative")
    return result


def _prices(item: dict[str, Any]) -> tuple[float, float]:
    values = item.get("excel_prices") or item
    return (
        _number(values.get("manufactured_price"), field="manufactured_price"),
        _number(values.get("market_average_price") or 0, field="market_average_price"),
    )


def _listing_audit(
    product: dict[str, Any], channel: str, listing: dict[str, Any]
) -> tuple[dict[str, Any], MatchResult]:
    result = validate_match(
        brand=str(product["brand_name"]),
        product_name=str(product["product_name"]),
        target_size_text=product.get("size"),
        candidate_name=str(listing.get("matched_title") or ""),
        candidate_context=" ".join(
            str(value or "") for value in (listing.get("seller"), listing.get("url"))
        ),
        candidate_size_text=listing.get("size"),
    )
    audit = {
        "row": product["row"],
        "product_name": product["product_name"],
        "size": product.get("size", ""),
        "source": channel,
        "accepted": result.accepted,
        "active": listing.get("available") is not False,
        "score": result.score,
        "candidate": listing.get("matched_title") or "",
        "candidate_size": listing.get("size") or "",
        "url": listing.get("url") or "",
        "price": listing.get("price"),
        "reasons": result.reasons,
    }
    return audit, result


def build_public_data(
    research: dict[str, Any], *, strict: bool = True
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    products: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []

    raw_products = research.get("products", [])
    seen_row_ids: set[int] = set()
    for item in raw_products:
        try:
            row_id = int(item["row"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("product row ID must be an integer") from exc
        if row_id <= 0:
            raise ValueError(f"product row ID must be positive: {row_id}")
        if row_id in seen_row_ids:
            raise ValueError(f"duplicate product row ID: {row_id}")
        seen_row_ids.add(row_id)

    for item in sorted(raw_products, key=lambda product: int(product["row"])):
        mfg_price, reference_price = _prices(item)
        active_sources: dict[str, dict[str, Any]] = {}

        raw_sources = item.get("sources", {})
        ordered_channels = sorted(
            raw_sources,
            key=lambda channel: (CHANNEL_RANK.get(channel, len(CHANNEL_ORDER)), channel),
        )
        for channel in ordered_channels:
            raw_listing = raw_sources[channel]
            listing = dict(raw_listing)
            audit_row, match = _listing_audit(item, channel, listing)
            audit.append(audit_row)

            if listing.get("available") is False:
                continue
            if not match.accepted:
                violations.append(
                    {
                        "row": item["row"],
                        "product_name": item["product_name"],
                        "channel": channel,
                        "reasons": match.reasons,
                    }
                )
                if strict:
                    continue

            price = _number(listing.get("price"), field=f"row {item['row']} {channel} price")
            if price <= 0:
                raise ValueError(f"row {item['row']} {channel} price must be positive")
            confidence = _number(
                listing.get("confidence", 100),
                field=f"row {item['row']} {channel} confidence",
            )
            if confidence > 100:
                raise ValueError(f"row {item['row']} {channel} confidence cannot exceed 100")
            url = str(listing.get("url") or "")
            if not url.startswith(("https://", "http://")):
                reason = "listing URL must be HTTP(S)"
                violations.append(
                    {
                        "row": item["row"],
                        "product_name": item["product_name"],
                        "channel": channel,
                        "reasons": [reason],
                    }
                )
                if strict:
                    continue
            listing["price"] = price
            listing["confidence"] = confidence
            listing["available"] = True
            active_sources[channel] = listing

        # MRP for a local SKU is the workbook's Mkt (Avg) Price, full stop.
        #
        # The workbook is the commercial source of truth: its cost basis is a
        # trade discount off exactly this number (40%/30%/25% -> cost/MRP ratios
        # of 0.60/0.70/0.75), so replacing it with a scraped brand-store price
        # breaks that arithmetic. A brand's own site runs promotions, and the
        # discounted checkout price it advertises is frequently BELOW our
        # sourcing cost -- which made six SKUs read as instant losses and
        # inflated the "above market" count by 91.
        #
        # Scraped listings still travel with the product; they are shown in
        # their own channel columns, with their live deep links intact. They
        # just no longer overwrite the benchmark they are meant to be compared
        # against.
        mrp = reference_price
        mrp_source_type = "workbook"
        if mrp <= 0:
            violations.append(
                {
                    "row": int(item["row"]),
                    "channel": "-",
                    "reasons": [
                        "local SKU has no workbook MRP benchmark; "
                        "cannot establish a market reference price"
                    ],
                }
            )

        products.append(
            {
                "row": int(item["row"]),
                "product_name": item["product_name"],
                "brand_name": item["brand_name"],
                "size": item.get("size", ""),
                "manufactured_price": mfg_price,
                "market_average_price": round(mrp, 4),
                "canonical_name": item.get("canonical_name") or item["product_name"],
                "sources": active_sources,
                "mrp_source_type": mrp_source_type,
            }
        )

    if strict and violations:
        raise CatalogValidationError(violations)

    source_counts = Counter(channel for product in products for channel in product["sources"])
    discovered = set(source_counts)
    source_columns = [channel for channel in CHANNEL_ORDER if channel in discovered]
    source_columns.extend(sorted(discovered - set(source_columns)))
    coverage_counts = Counter(str(len(product["sources"])) for product in products)

    output = {
        "currency": research.get("currency", "BDT"),
        "currency_symbol": research.get("currency_symbol", "৳"),
        "source_excel": research.get("source_excel", "product_marketplace_price_comparison.xlsx"),
        "internal_price_basis": research.get("internal_price_basis", ""),
        "matching_policy": research.get("matching_policy", {}),
        "generated_at": research.get("generated_at") or "2026-09-02T00:00:00Z",
        "product_count": len(products),
        "brand_count": len({product["brand_name"] for product in products}),
        "source_columns": source_columns,
        "source_listing_counts": {channel: source_counts[channel] for channel in source_columns},
        "coverage_counts": dict(sorted(coverage_counts.items(), key=lambda item: int(item[0]))),
        "products": products,
    }
    return output, audit


def _sql_text(value: Any) -> str:
    return "'" + str(value or "").replace("'", "''") + "'"


def _sql_number(value: Any) -> str:
    return repr(float(value))


def generate_seed_sql(output: dict[str, Any]) -> str:
    defaults = DEFAULT_GLOBAL_PARAMS
    lines = [
        "PRAGMA foreign_keys = ON;",
        "BEGIN TRANSACTION;",
        (
            "INSERT INTO global_pricing_params "
            "(id, packaging, transport, delivery, cac, target_margin_pct, discount_type, discount_val) "
            f"VALUES (1, {defaults['packaging']}, {defaults['transport']}, "
            f"{defaults['delivery']}, {defaults['cac']}, {defaults['targetMarginPct']}, "
            f"{_sql_text(defaults['discountType'])}, {defaults['discountVal']}) "
            "ON CONFLICT(id) DO NOTHING;"
        ),
        "DELETE FROM marketplace_listings WHERE row_id IN (SELECT row_id FROM products WHERE sourcing_origin = 'local');",
    ]

    row_ids: list[str] = []
    for product in output["products"]:
        row_id = int(product["row"])
        row_ids.append(str(row_id))
        lines.append(
            "INSERT INTO products "
            "(row_id, product_name, brand_name, size, manufactured_price, market_average_price, canonical_name, mrp_source_type, sourcing_origin) "
            f"VALUES ({row_id}, {_sql_text(product['product_name'])}, {_sql_text(product['brand_name'])}, "
            f"{_sql_text(product.get('size'))}, {_sql_number(product['manufactured_price'])}, "
            f"{_sql_number(product['market_average_price'])}, {_sql_text(product.get('canonical_name'))}, "
            f"{_sql_text(product.get('mrp_source_type'))}, 'local') "
            "ON CONFLICT(row_id) DO UPDATE SET product_name=excluded.product_name, "
            "brand_name=excluded.brand_name, size=excluded.size, "
            "manufactured_price=excluded.manufactured_price, "
            "market_average_price=excluded.market_average_price, "
            "canonical_name=excluded.canonical_name, mrp_source_type=excluded.mrp_source_type, "
            "sourcing_origin=excluded.sourcing_origin;"
        )
        for channel, listing in product.get("sources", {}).items():
            # A listing is verified when it was confirmed against a live product
            # page, which requires a URL. The schema enforces that pairing, and
            # the UI shows the deep link only for verified rows — so the flag has
            # to be written here rather than left to the column default.
            verified = 1 if listing.get("url") else 0
            lines.append(
                "INSERT INTO marketplace_listings "
                "(row_id, channel_name, price, url, matched_title, size, seller, confidence, available, verified) "
                f"VALUES ({row_id}, {_sql_text(channel)}, {_sql_number(listing['price'])}, "
                f"{_sql_text(listing.get('url'))}, {_sql_text(listing.get('matched_title'))}, "
                f"{_sql_text(listing.get('size'))}, {_sql_text(listing.get('seller'))}, "
                f"{_sql_number(listing.get('confidence', 100))}, 1, {verified});"
            )

    lines.append(f"DELETE FROM products WHERE sourcing_origin = 'local' AND row_id NOT IN ({', '.join(row_ids)});")
    lines.extend(["COMMIT;", ""])
    return "\n".join(lines)


def write_artifacts(*, strict: bool = True) -> dict[str, Any]:
    research = json.loads(RESEARCH_PATH.read_text(encoding="utf-8"))
    output, audit = build_public_data(research, strict=strict)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

    json_text = json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    JSON_PATH.write_text(json_text, encoding="utf-8")
    PUBLIC_JSON_PATH.write_text(json_text, encoding="utf-8")
    AUDIT_PATH.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SEED_PATH.write_text(generate_seed_sql(output), encoding="utf-8")

    return {
        "status": "ok",
        "products": output["product_count"],
        "listings": sum(output["source_listing_counts"].values()),
        "json": str(JSON_PATH),
        "seed": str(SEED_PATH),
    }
