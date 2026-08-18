import json
from pathlib import Path

root = Path('/home/soyab/Downloads/product_pricing_visualization')
research = json.loads((root / 'verified_marketplace_research.json').read_text(encoding='utf-8'))

lines = []

# 1. Insert default global pricing params
lines.append("INSERT OR REPLACE INTO global_pricing_params (id, packaging, transport, delivery, cac, target_margin_pct, discount_type, discount_val) VALUES (1, 20.0, 40.0, 60.0, 80.0, 25.0, 'pct', 10.0);")

# 2. Insert products and marketplace listings
for p in research['products']:
    row_id = p['row']
    name = p['product_name'].replace("'", "''")
    brand = p['brand_name'].replace("'", "''")
    size = (p.get('size') or '').replace("'", "''")
    mfg = float(p['excel_prices'].get('manufactured_price') or 0)
    mkt = float(p['excel_prices'].get('market_average_price') or 0)
    canonical = (p.get('canonical_name') or '').replace("'", "''")
    
    lines.append(f"INSERT OR REPLACE INTO products (row_id, product_name, brand_name, size, manufactured_price, market_average_price, canonical_name) VALUES ({row_id}, '{name}', '{brand}', '{size}', {mfg}, {mkt}, '{canonical}');")
    
    for ch, data in p.get('sources', {}).items():
        ch_name = ch.replace("'", "''")
        price = float(data.get('price') or 0)
        url = (data.get('url') or '').replace("'", "''")
        matched_title = (data.get('matched_title') or '').replace("'", "''")
        l_size = (data.get('size') or '').replace("'", "''")
        seller = (data.get('seller') or '').replace("'", "''")
        conf = float(data.get('confidence') or 100.0)
        avail = 1 if data.get('available') is not False else 0
        
        lines.append(f"INSERT OR REPLACE INTO marketplace_listings (row_id, channel_name, price, url, matched_title, size, seller, confidence, available) VALUES ({row_id}, '{ch_name}', {price}, '{url}', '{matched_title}', '{l_size}', '{seller}', {conf}, {avail});")

# done appending

(root / 'seed.sql').write_text('\n'.join(lines), encoding='utf-8')
print(f"Generated seed.sql with {len(lines)} SQL statements.")
