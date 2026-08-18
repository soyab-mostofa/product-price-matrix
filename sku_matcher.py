from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re
import unicodedata
from rapidfuzz import fuzz

REPLACEMENTS = {
    'colour': 'color',
    'kajol': 'kajal',
    'khol': 'kajal',
    'rosemerry': 'rosemary',
    'miceller': 'micellar',
    'aloevera': 'aloe vera',
    'appricot': 'apricot',
    'worm porcelain': 'warm porcelain',
    'water proof': 'waterproof',
    'water-proof': 'waterproof',
    'tea tee': 'tea tree',
    'hydro boost': 'hydroboost',
    'hairfall': 'hair fall',
    'hand-made': 'handmade',
}

BRAND_MAP = {
    'Bio-Screen': [('bio screen',), ('bioscreen',)],
    'BioCare': [('biocare',), ('bio care',)],
    'Guerniss': [('guerniss',)],
    'Neofarmers': [('neofarmers',), ('neo farmers',)],
    'Skin Cafe': [('skin cafe',), ('skincafe',), ('skin cafe',)],
    'Enso Skin': [('enso skin',), ('enso',)],
    'RAJKONNA': [('rajkonna',)],
    'LILAC': [('lilac',)],
    'Hawaa': [('hawaa',)],
    'Nirvana': [('nirvana color',), ('nirvana',)],
    'Groome': [('groome',)],
    'Lavino': [('lavino',)],
    'Ombre': [('ombre',)],
    'Panam': [('panam',)],
}
Q_SUBBRANDS = {
    'nature beauty': [('nature beauty',)],
    'quinsia': [('quinsia',)],
    'qolore': [('qolore',)],
    'qluxury': [('qluxury',), ('q luxury',)],
    'apple colour': [('apple colour',), ('apple color',)],
}

GRAMMAR_STOP = {
    'and', 'with', 'for', 'the', 'of', 'a', 'an', 'plus', 'by', 'to', 'from',
    'online', 'best', 'price', 'bangladesh', 'buy', 'now', 'new',
}
TYPE_STOP = {
    'facial', 'face', 'wash', 'cleanser', 'cleansing', 'foam', 'toner', 'serum',
    'essence', 'cream', 'gel', 'moisturizer', 'moisturiser', 'moisturizing',
    'moisturising', 'lotion', 'oil', 'shampoo', 'conditioner', 'scrub', 'mask',
    'soap', 'bar', 'beauty', 'sunscreen', 'sunblock', 'lipstick', 'lip', 'balm',
    'gloss', 'glaze', 'foundation', 'powder', 'concealer', 'mascara', 'kajal',
    'eyeliner', 'nail', 'enamel', 'mist', 'perfume', 'spray', 'water', 'pads',
    'pad', 'razor', 'strips', 'strip', 'wipes', 'body', 'hand', 'air', 'freshener',
}
VARIANT_GENERIC = TYPE_STOP | {
    'color', 'soft', 'matte', 'liquid', 'full', 'cover', 'perfect', 'pro', 'compact',
    'vacation', 'holding', 'bullet', 'makeup', 'waterproof', 'glitter', 'eau', 'de',
    'parfum', 'women', 'woman', 'man', 'men', 'perfumed', 'mini', 'deep', 'light',
}

TYPE_PATTERNS = [
    ('micellar_water', [r'\bmicellar water\b']),
    ('rose_water', [r'\brose water\b']),
    ('facial_cleanser', [r'\bface ?wash\b', r'\bfacial wash\b', r'\bfacial cleanser\b', r'\bfoam cleanser\b', r'\bcleansing gel\b', r'\bface cleanser\b', r'\bcleanser\b']),
    ('toner', [r'\btoner\b']),
    ('hair_serum', [r'\bhair serum\b']),
    ('serum', [r'\bserum\b']),
    ('essence', [r'\bessence\b']),
    ('sunscreen', [r'\bsunscreen\b', r'\bsun ?block\b']),
    ('shampoo_conditioner', [r'\bshampoo (?:and|with|\+) conditioner\b', r'\bshampoo & conditioner\b']),
    ('shampoo', [r'\bshampoo\b']),
    ('conditioner', [r'\bconditioner\b']),
    ('essential_oil', [r'\bessential oil\b']),
    ('hair_oil', [r'\bhair (?:growth )?oil\b', r'\bonion seed hair oil\b']),
    ('body_oil', [r'\bbody oil\b', r'\bface & body oil\b', r'\bface and body oil\b']),
    ('oil', [r'\boil\b']),
    ('body_lotion', [r'\bbody lotion\b']),
    ('baby_lotion', [r'\bbaby body lotion\b']),
    ('moisturizer', [r'\bmoisturizer\b', r'\bmoisturiser\b', r'\bmoisturizing gel\b', r'\bmoisturising gel\b', r'\bday cream\b', r'\bnight repairing cream\b', r'\bface cream\b', r'\bfacial cream\b', r'\bneck cream\b', r'\bmoisturizing cream\b', r'\bmoisturising cream\b']),
    ('cream', [r'\bcream\b']),
    ('shower_gel', [r'\bshower gel\b']),
    ('hand_wash', [r'\bhand ?wash\b']),
    ('air_freshener', [r'\bair freshener\b']),
    ('soap', [r'\bbeauty bar\b', r'\bbaby bar\b', r'\bsoap\b']),
    ('scrub', [r'\bscrub\b']),
    ('sheet_mask', [r'\bsheet mask\b']),
    ('mask', [r'\bmask\b']),
    ('lip_gloss', [r'\blip glaze\b', r'\blip gloss\b']),
    ('lip_balm', [r'\blip ?balm\b']),
    ('lipstick', [r'\blipstick\b', r'\bmatte color bullet\b']),
    ('foundation', [r'\bfoundation\b']),
    ('pressed_powder', [r'\bpressed powder\b', r'\bcompact powder\b']),
    ('concealer', [r'\bconcealer\b']),
    ('mascara', [r'\bmascara\b']),
    ('kajal', [r'\bkajal\b', r'\bkohl\b']),
    ('eyeliner', [r'\beye ?liner\b']),
    ('nail_enamel', [r'\bnail enamel\b']),
    ('face_palette', [r'\bface palette\b']),
    ('setting_spray', [r'\bsetting spray\b']),
    ('body_mist', [r'\bbody mist\b']),
    ('perfume', [r'\bperfume\b', r'\beau de parfum\b', r'\bedp\b']),
    ('wet_wipes', [r'\bwet wipes\b']),
    ('cotton_pad', [r'\bcotton pads?\b']),
    ('razor', [r'\brazor\b']),
    ('nose_strip', [r'\bnose strips?\b']),
    ('beauty_blender', [r'\b(?:beauty|makeup) blender\b', r'\bblender sponge\b']),
    ('glycerin', [r'\bglycerin\b']),
    ('powder', [r'\bpowder\b']),
]
VARIANT_TYPES = {'lip_gloss', 'lip_balm', 'lipstick', 'foundation', 'pressed_powder', 'concealer', 'nail_enamel', 'face_palette', 'body_mist', 'perfume'}


def normalize(value: str | None) -> str:
    text = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode('ascii').casefold()
    text = text.replace('&', ' and ').replace('+', ' plus ')
    text = text.replace("'", '')
    for old, new in REPLACEMENTS.items():
        text = text.replace(old, new)
    # Guerniss concealer codes are commonly typed as GO21/GO22/GO23 in sheets,
    # while official catalogs use G021/G022/G023 (zero, not letter O).
    text = re.sub(r'\bgo(?=\d)', 'g0', text)
    text = re.sub(r'(?<=\d)\s*%\b', ' percent', text)
    text = re.sub(r'[^a-z0-9.]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def compact(value: str | None) -> str:
    return re.sub(r'[^a-z0-9]', '', normalize(value))


def brand_aliases(brand: str, product_name: str) -> list[str]:
    if brand == 'Q Cosmetics':
        n = normalize(product_name)
        for subbrand, aliases in Q_SUBBRANDS.items():
            if subbrand in n:
                return [a[0] for a in aliases]
        return ['q cosmetics']
    options = BRAND_MAP.get(brand, [(normalize(brand),)])
    return [option[0] for option in options]


def brand_matches(brand: str, product_name: str, candidate_text: str) -> bool:
    c_norm = normalize(candidate_text)
    c_compact = compact(candidate_text)
    return any(alias in c_norm or compact(alias) in c_compact for alias in brand_aliases(brand, product_name))


def parse_sizes(value: str | None) -> set[tuple[Decimal, str]]:
    text = normalize(value)
    sizes: set[tuple[Decimal, str]] = set()
    pattern = r'(?<![a-z0-9.])(\d+(?:\.\d+)?)\s*(milliliters?|ml|grams?|grammes?|gm|g|kilograms?|kg|liters?|litres?|l|pieces?|pcs?|pc)\b'
    for number, unit in re.findall(pattern, text):
        amount = Decimal(number)
        u = unit
        if u in {'gram', 'grams', 'gramme', 'grammes', 'gm', 'g'}:
            u = 'g'
        elif u in {'milliliter', 'milliliters', 'ml'}:
            u = 'ml'
        elif u in {'kilogram', 'kilograms', 'kg'}:
            amount *= Decimal('1000'); u = 'g'
        elif u in {'liter', 'liters', 'litre', 'litres', 'l'}:
            amount *= Decimal('1000'); u = 'ml'
        else:
            u = 'pcs'
        sizes.add((amount.normalize(), u))
    return sizes


def primary_size(value: str | None) -> tuple[Decimal, str] | None:
    sizes = parse_sizes(value)
    return sorted(sizes, key=lambda item: (item[1], item[0]))[0] if sizes else None


def detect_type(value: str | None) -> str | None:
    text = normalize(value)
    for product_type, patterns in TYPE_PATTERNS:
        if any(re.search(pattern, text) for pattern in patterns):
            return product_type
    return None


def types_compatible(target_type: str | None, candidate_type: str | None) -> bool:
    if not target_type or not candidate_type:
        return target_type == candidate_type or candidate_type is None
    if target_type == candidate_type:
        return True
    compatible_groups = [
        {'cream', 'moisturizer'},
        {'oil', 'body_oil', 'essential_oil', 'hair_oil'},
    ]
    return any(target_type in group and candidate_type in group for group in compatible_groups)


def is_bundle(value: str | None) -> bool:
    text = normalize(value)
    return bool(re.search(r'\b(combo|duo|set|buy 1|get 1|b1g1|pack of [2-9]|[2-9] ?pcs combo)\b', text))


def critical_markers(value: str | None, size: tuple[Decimal, str] | None = None) -> set[str]:
    text = normalize(value)
    markers = set()
    for number in re.findall(r'\b(\d+(?:\.\d+)?)\s*percent\b', text):
        markers.add(f'{number}percent')
    for number in re.findall(r'\bspf\s*(\d+)\b', text):
        markers.add(f'spf{number}')
    for prefix, number in re.findall(r'\b(nc|bb|go|g|wlg)\s*(\d{1,3})\b', text):
        markers.add(f'{prefix}{number}')
    if detect_type(text) in VARIANT_TYPES:
        for number in re.findall(r'(?<![a-z])\b(\d{1,3}(?:\.\d+)?)\b', text):
            if size is None or Decimal(number) != size[0]:
                markers.add(number)
    return markers


def variant_tokens(brand: str, product_name: str, size: tuple[Decimal, str] | None) -> set[str]:
    product_type = detect_type(product_name)
    if product_type not in VARIANT_TYPES:
        return set()
    tokens = set(normalize(product_name).split())
    for alias in brand_aliases(brand, product_name):
        tokens -= set(normalize(alias).split())
    tokens -= GRAMMAR_STOP
    tokens -= VARIANT_GENERIC
    tokens -= {'spf', 'pa'}
    if size is not None:
        tokens.discard(str(size[0]))
        tokens.discard(str(size[0].normalize()))
    return {token for token in tokens if len(token) >= 2 or token.isdigit()}


def significant_tokens(brand: str, product_name: str, size: tuple[Decimal, str] | None) -> set[str]:
    tokens = set(normalize(product_name).split())
    for alias in brand_aliases(brand, product_name):
        tokens -= set(normalize(alias).split())
    tokens -= GRAMMAR_STOP
    tokens -= TYPE_STOP
    tokens -= {'ml', 'gm', 'g', 'kg', 'pcs', 'pc', 'percent', 'spf', 'pa'}
    if size is not None:
        tokens.discard(str(size[0]))
        tokens.discard(str(size[0].normalize()))
    return {token for token in tokens if len(token) >= 2 or token.isdigit()}


@dataclass
class MatchResult:
    accepted: bool
    score: float
    reasons: list[str]


def validate_match(*, brand: str, product_name: str, target_size_text: str | None, candidate_name: str, candidate_context: str = '', candidate_size_text: str | None = None) -> MatchResult:
    reasons: list[str] = []
    target_size = primary_size(target_size_text)
    candidate_sizes = parse_sizes(' '.join(filter(None, [candidate_name, candidate_size_text])))
    target_type = detect_type(product_name)
    candidate_type = detect_type(candidate_name)
    all_candidate_text = f'{candidate_name} {candidate_context}'

    if not brand_matches(brand, product_name, all_candidate_text):
        reasons.append('brand mismatch')
    if is_bundle(candidate_name) != is_bundle(product_name):
        reasons.append('bundle/single mismatch')
    if target_type and not types_compatible(target_type, candidate_type):
        reasons.append(f'product type mismatch ({target_type} != {candidate_type})')
    if target_size is not None:
        if not candidate_sizes:
            reasons.append('candidate size missing')
        elif target_size not in candidate_sizes:
            reasons.append(f'size mismatch ({target_size} not in {sorted(candidate_sizes)})')

    c_compact = compact(candidate_name)
    markers = critical_markers(product_name, target_size)
    missing_markers = sorted(marker for marker in markers if compact(marker) not in c_compact)
    if missing_markers:
        reasons.append(f'missing critical markers: {missing_markers}')

    variants = variant_tokens(brand, product_name, target_size)
    c_tokens = set(normalize(candidate_name).split())
    missing_variants = sorted(token for token in variants if token not in c_tokens and compact(token) not in c_compact)
    if missing_variants:
        reasons.append(f'variant mismatch: {missing_variants}')

    target_tokens = significant_tokens(brand, product_name, target_size)
    coverage = len(target_tokens & c_tokens) / len(target_tokens) if target_tokens else 1.0
    similarity = fuzz.token_set_ratio(normalize(product_name), normalize(candidate_name)) / 100.0
    score = round((coverage * 0.68 + similarity * 0.32) * 100, 2)
    if coverage < 0.66 and similarity < 0.90:
        reasons.append(f'name coverage too low ({coverage:.2f}, similarity {similarity:.2f})')

    return MatchResult(not reasons, score, reasons)
