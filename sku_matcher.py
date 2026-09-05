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
    'glutathion': 'glutathione',
    'deo': 'deodorant',
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
    'Orgagenic': [('orgagenic',)],
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
    'uk', 'usa', 'india', 'thai', 'thailand', 'france', 'germany', 'malaysia', 'bd', 'official',
}
TYPE_STOP = {
    'facial', 'face', 'wash', 'cleanser', 'cleansing', 'foam', 'toner', 'serum',
    'essence', 'cream', 'gel', 'moisturizer', 'moisturiser', 'moisturizing',
    'moisturising', 'lotion', 'oil', 'shampoo', 'conditioner', 'scrub', 'mask',
    'soap', 'bar', 'beauty', 'sunscreen', 'sunblock', 'lipstick', 'lip', 'balm',
    'gloss', 'glaze', 'foundation', 'powder', 'concealer', 'mascara', 'kajal',
    'eyeliner', 'nail', 'enamel', 'mist', 'perfume', 'spray', 'water', 'pads',
    'pad', 'razor', 'strips', 'strip', 'wipes', 'body', 'hand', 'air', 'freshener',
    'perfumed',
}
VARIANT_GENERIC = TYPE_STOP | {
    'color', 'soft', 'matte', 'liquid', 'full', 'cover', 'perfect', 'pro', 'compact',
    'vacation', 'holding', 'bullet', 'makeup', 'waterproof', 'glitter', 'eau', 'de',
    'parfum', 'women', 'woman', 'man', 'men', 'perfumed', 'mini', 'deep', 'light',
}

TYPE_PATTERNS = [
    ('micellar_water', [r'\bmicellar water\b']),
    ('rose_water', [r'\brose water\b']),
    ('facial_cleanser', [r'\bface ?wash\b', r'\bfacial wash\b', r'\bfacial cleanser\b', r'\bfoam cleanser\b', r'\bcleansing gel\b', r'\bface cleanser\b', r'\bcleanser\b', r'\bfacial foam\b', r'\bface foam\b', r'\bfoaming cleanser\b', r'\bcleansing foam\b']),
    ('toner', [r'\btoner\b']),
    ('hair_serum', [r'\bhair serum\b']),
    ('serum', [r'\bserum\b']),
    ('essence', [r'\bessence\b']),
    ('sunscreen', [r'\bsunscreen\b', r'\bsun ?block\b', r'\bsun cream\b']),
    ('shampoo_conditioner', [r'\bshampoo (?:and|with|\+) conditioner\b', r'\bshampoo & conditioner\b', r'\b2in1 shampoo \+ conditioner\b', r'\b2 in 1 shampoo\b']),
    ('shampoo', [r'\bshampoo\b']),
    ('conditioner', [r'\bconditioner\b', r'\bconditioning smoothies\b']),
    ('essential_oil', [r'\bessential oil\b']),
    ('hair_oil', [r'\bhair (?:growth )?oil\b', r'\bonion seed hair oil\b']),
    ('body_oil', [r'\bbody oil\b', r'\bface & body oil\b', r'\bface and body oil\b']),
    ('oil', [r'\boil\b']),
    ('petroleum_jelly', [r'\bblueseal\b', r'\bpetroleum jelly\b']),
    ('body_lotion', [r'\bbody lotion\b', r'\bserum burst lotion\b', r'\bmoisturising lotion\b', r'\bmoisturizing lotion\b', r'\bmoisture lotion\b', r'\bbody milk\b']),
    ('baby_lotion', [r'\bbaby body lotion\b', r'\bbaby lotion\b']),
    ('night_cream', [r'\bnight (?:repairing |comfort )?cream\b', r'\bnight gel\b']),
    ('day_cream', [r'\bday cream\b']),
    ('moisturizer', [r'\bmoisturizer\b', r'\bmoisturiser\b', r'\bmoisturizing gel\b', r'\bmoisturising gel\b', r'\bface cream\b', r'\bfacial cream\b', r'\bneck cream\b', r'\bmoisturizing cream\b', r'\bmoisturising cream\b', r'\bsoothing gel\b']),
    ('hair_mask', [r'\bhair mask\b']),
    ('cream', [r'\bcream\b', r'\bbeauty cream\b']),
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
    ('deo_roll_on', [r'\broll\s*on\b']),
    ('body_spray', [r'\bbody spray\b', r'\bdeodorant (?:body )?spray\b', r'\bdeo spray\b', r'\bpocket deodorant\b', r'\bbody deodorant\b', r'\bdeodorant\b', r'\bdeo\b']),
    ('perfume', [r'\bperfume\b', r'\beau de parfum\b', r'\bedp\b', r'\bedt\b']),
    ('wet_wipes', [r'\bwet wipes\b']),
    ('cotton_pad', [r'\bcotton pads?\b']),
    ('razor', [r'\brazor\b']),
    ('nose_strip', [r'\bnose strips?\b']),
    ('beauty_blender', [r'\b(?:beauty|makeup) blender\b', r'\bblender sponge\b']),
    ('glycerin', [r'\bglycerin\b']),
    ('powder', [r'\bpowder\b']),
]
VARIANT_TYPES = {
    'lip_gloss', 'lip_balm', 'lipstick', 'foundation', 'pressed_powder',
    'concealer', 'nail_enamel', 'face_palette', 'body_mist', 'body_spray',
    'deo_roll_on', 'perfume', 'petroleum_jelly',
}
SHADE_TOKENS = {
    'natural', 'ivory', 'pink', 'porcelain', 'beige', 'medium', 'tan', 'warm',
    'light', 'fair', 'deep', 'dark', 'nude', 'rose', 'red', 'coral', 'brown',
    'plum', 'mauve', 'peach', 'orange', 'maroon', 'berry', 'wine', 'golden',
}


def normalize(value: str | None) -> str:
    text = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode('ascii').casefold()
    text = text.replace('&', ' and ').replace('+', ' plus ')
    text = text.replace("'", '')
    for old, new in REPLACEMENTS.items():
        text = text.replace(old, new)
    # Guerniss concealer codes are commonly typed as GO21/GO22/GO23 in sheets,
    # while official catalogs use G021/G022/G023 (zero, not letter O).
    text = re.sub(r'\bgo(?=\d)', 'g0', text)
    text = re.sub(r'(?<=\d)\s*%', ' percent', text)
    text = re.sub(r'[^a-z0-9.]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def compact(value: str | None) -> str:
    return re.sub(r'[^a-z0-9]', '', normalize(value))


def brand_aliases(brand: str, product_name: str) -> list[str]:
    if brand == 'Q Cosmetics':
        n = normalize(product_name)
        for subbrand, aliases in Q_SUBBRANDS.items():
            if normalize(subbrand) in n:
                return [a[0] for a in aliases]
        return ['q cosmetics']
    options = BRAND_MAP.get(brand, [(normalize(brand),)])
    return [option[0] for option in options]


def brand_matches(brand: str, product_name: str, candidate_text: str) -> bool:
    c_norm = normalize(candidate_text)
    c_compact = compact(candidate_text)
    return any(alias in c_norm or compact(alias) in c_compact for alias in brand_aliases(brand, product_name))


def has_conflicting_title_brand(brand: str, product_name: str, candidate_name: str) -> bool:
    if brand_matches(brand, product_name, candidate_name):
        return False
    candidate_norm = normalize(candidate_name)
    candidate_compact = compact(candidate_name)
    expected = {normalize(alias) for alias in brand_aliases(brand, product_name)}
    known_groups = [
        {normalize(option[0]) for option in options}
        for options in BRAND_MAP.values()
    ] + [
        {normalize(option[0]) for option in options}
        for options in Q_SUBBRANDS.values()
    ]
    for aliases in known_groups:
        if aliases & expected:
            continue
        if any(alias in candidate_norm or compact(alias) in candidate_compact for alias in aliases):
            return True
    return False


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
    if target_type is None:
        return candidate_type is None
    if candidate_type is None:
        return False
    if target_type == candidate_type:
        return True
    if {target_type, candidate_type} <= {'cream', 'moisturizer', 'day_cream'}:
        return True
    if {target_type, candidate_type} <= {'body_lotion', 'baby_lotion'}:
        return True
    oil_types = {'oil', 'body_oil', 'hair_oil', 'essential_oil'}
    return 'oil' in {target_type, candidate_type} and {target_type, candidate_type} <= oil_types


def is_bundle(value: str | None) -> bool:
    text = normalize(value)
    patterns = [
        r'\b(combo|duo|bundle|set)\b',
        r'\bbogo(?: offer)?\b',
        r'\bbuy\b.{0,80}\bget\b.{0,80}\bfree\b',
        r'\bwith\s+(?:a\s+)?free\b',
        r'\bfree\s+(?:gift|loofah|conditioner|shampoo|item|product)\b',
        r'\bpack of\s+(?:[2-9]|\d{2,})\b',
        r'\b(?:[2-9]|\d{2,})\s*pcs?\b',
    ]
    return any(re.search(pattern, text) for pattern in patterns)


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
        text_without_sizes = re.sub(
            r'\b\d+(?:\.\d+)?\s*(?:milliliters?|ml|grams?|grammes?|gm|g|kilograms?|kg|liters?|litres?|l|pieces?|pcs?|pc)\b',
            ' ',
            text,
        )
        prefixed_numbers = {
            match.group(2)
            for match in re.finditer(r'\b(nc|bb|go|g|wlg|spf)\s*(\d{1,3})\b', text)
        }
        for number in re.findall(r'(?<![a-z])\b(\d{1,3}(?:\.\d+)?)\b', text_without_sizes):
            if number in prefixed_numbers:
                continue
            if size is None or Decimal(number) != size[0]:
                markers.add(number)
    return markers


KEY_ACTIVES = {
    'hyaluronic': {'hyaluronic', 'ha'},
    'salicylic': {'salicylic', 'bha'},
    'glycolic': {'glycolic', 'aha'},
    'niacinamide': {'niacinamide'},
    'retinol': {'retinol', 'retinoid'},
    'ceramide': {'ceramide', 'ceramides'},
    'glutathione': {'glutathione'},
    'alpha arbutin': {'alpha arbutin', 'arbutin'},
    'vitamin c': {'vitamin c', 'ascorbic'},
    'cica': {'cica', 'centella'},
    'snail': {'snail', 'mucin'},
    'collagen': {'collagen'},
}

FRAGRANCE_VARIANTS = {
    'enticing', 'romantic', 'gorgeous', 'alluring', 'charming',
    'royal intense', 'classic gold', 'aqua kiss', 'cocoa butter', 'cocoa glow', 'cocoa', 'original',
}


def detect_actives(text: str | None) -> set[str]:
    if not text:
        return set()
    norm = normalize(text)
    found = set()
    for active, aliases in KEY_ACTIVES.items():
        if any(re.search(r'\b' + re.escape(alias) + r'\b', norm) for alias in aliases):
            found.add(active)
    return found


def detect_fragrances(text: str | None) -> set[str]:
    if not text:
        return set()
    norm = normalize(text)
    found = set()
    for f in FRAGRANCE_VARIANTS:
        if re.search(r'\b' + re.escape(f) + r'\b', norm):
            found.add(f)
    return found


HAIR_VARIANTS = {
    'volume': ['volume'],
    'anti_dandruff': ['anti dandruff', 'dandruff'],
    'hair_fall': ['hair fall', 'anti hair fall', 'rambut gugur'],
    'damage_restore': ['damage restore'],
    'smooth_manageable': ['smooth & manageable', 'smooth and manageable'],
    'perfect_straight': ['perfect straight'],
    'colour_protect': ['colour protect', 'color protect', 'color protecting', 'colour protecting'],
    'purple': ['purple', 'anti brassiness'],
}


def detect_hair_variants(text: str | None) -> set[str]:
    if not text:
        return set()
    norm = normalize(text)
    found = set()
    for v_key, patterns in HAIR_VARIANTS.items():
        if any(re.search(r'\b' + re.escape(p) + r'\b', norm) for p in patterns):
            found.add(v_key)
    return found


# Brands ship several products that differ only by a sub-line word, with every
# other token shared: Streax *Vitalized* vs *Shine*, Streax Pro Vitariche
# *Care* vs *Gloss*, Sunsilk *Hijab* vs the plain line. Token-set similarity
# rates these ~80% alike, so without an explicit rule they clear the score
# threshold and put a shopper on the wrong bottle. Members of one set are
# mutually exclusive.
SUB_LINES: tuple[set[str], ...] = (
    {'vitalized', 'shine', 'gloss', 'care'},   # Streax hair serum lines
    {'hijab', 'black shine', 'soft smooth'},   # Sunsilk sub-lines
)


def detect_sub_lines(text: str | None) -> set[tuple[int, str]]:
    if not text:
        return set()
    norm = f' {normalize(text)} '
    found = set()
    for index, group in enumerate(SUB_LINES):
        for member in group:
            if f' {member} ' in norm:
                found.add((index, member))
    return found


def variant_tokens(brand: str, product_name: str, size: tuple[Decimal, str] | None) -> set[str]:
    product_type = detect_type(product_name)
    if product_type not in VARIANT_TYPES:
        return set()
    text_without_sizes = re.sub(
        r'\b\d+(?:\.\d+)?\s*(?:milliliters?|ml|grams?|grammes?|gm|g|kilograms?|kg|liters?|litres?|l|pieces?|pcs?|pc)\b',
        ' ',
        normalize(product_name),
    )
    tokens = set(text_without_sizes.split())
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
    text_without_sizes = re.sub(
        r'\b\d+(?:\.\d+)?\s*(?:milliliters?|ml|grams?|grammes?|gm|g|kilograms?|kg|liters?|litres?|l|pieces?|pcs?|pc)\b',
        ' ',
        normalize(product_name),
    )
    tokens = set(text_without_sizes.split())
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
    candidate_title_sizes = parse_sizes(candidate_name)
    candidate_declared_sizes = parse_sizes(candidate_size_text)
    candidate_sizes = candidate_title_sizes | candidate_declared_sizes
    target_type = detect_type(product_name)
    candidate_type = detect_type(candidate_name)
    all_candidate_text = f'{candidate_name} {candidate_context}'

    if not brand_matches(brand, product_name, all_candidate_text):
        reasons.append('brand mismatch')
    if has_conflicting_title_brand(brand, product_name, candidate_name):
        reasons.append('conflicting brand in candidate title')
    if is_bundle(candidate_name) != is_bundle(product_name):
        reasons.append('bundle/single mismatch')
    candidate_package_sizes = {size for size in candidate_title_sizes if size[1] != 'pcs'}
    if not is_bundle(product_name) and len(candidate_package_sizes) > 1:
        reasons.append('multiple package sizes for single SKU')
    if target_type and not types_compatible(target_type, candidate_type):
        reasons.append(f'product type mismatch ({target_type} != {candidate_type})')
    elif candidate_type and not target_type and candidate_type in {'cream', 'night_cream', 'body_lotion', 'shampoo', 'conditioner', 'body_spray', 'deo_roll_on', 'perfume'}:
        reasons.append(f'unmatched candidate product type ({candidate_type})')
    if target_size is not None:
        if candidate_title_sizes and target_size not in candidate_title_sizes:
            reasons.append(f'title size mismatch ({target_size} not in {sorted(candidate_title_sizes)})')
        elif not candidate_title_sizes and not candidate_declared_sizes:
            reasons.append('candidate size missing')
        elif target_size not in candidate_sizes:
            reasons.append(f'size mismatch ({target_size} not in {sorted(candidate_sizes)})')

    target_actives = detect_actives(product_name)
    candidate_actives = detect_actives(candidate_name)
    missing_actives = target_actives - candidate_actives
    if missing_actives:
        reasons.append(f'missing key active: {sorted(missing_actives)}')

    target_fragrances = detect_fragrances(product_name)
    candidate_fragrances = detect_fragrances(candidate_name)
    missing_fragrances = target_fragrances - candidate_fragrances
    if missing_fragrances:
        reasons.append(f'missing fragrance variant: {sorted(missing_fragrances)}')
    unexpected_fragrances = candidate_fragrances - target_fragrances
    if unexpected_fragrances and (target_fragrances or target_type in {'petroleum_jelly', 'deo_roll_on', 'body_spray'}):
        reasons.append(f'unexpected conflicting fragrance: {sorted(unexpected_fragrances)}')

    target_hair = detect_hair_variants(product_name)
    candidate_hair = detect_hair_variants(candidate_name)
    missing_hair = target_hair - candidate_hair
    if missing_hair:
        reasons.append(f'missing hair variant: {sorted(missing_hair)}')
    unexpected_hair = candidate_hair - target_hair
    if unexpected_hair and target_hair:
        reasons.append(f'unexpected conflicting hair variant: {sorted(unexpected_hair)}')

    target_sub_lines = detect_sub_lines(product_name)
    candidate_sub_lines = detect_sub_lines(candidate_name)
    candidate_sub_groups = {group for group, _ in candidate_sub_lines}
    for group, member in target_sub_lines:
        rival = next(
            (other for other_group, other in candidate_sub_lines
             if other_group == group and other != member),
            None,
        )
        if rival is not None:
            reasons.append(f'sub-line mismatch ({member} != {rival})')
        elif group not in candidate_sub_groups:
            reasons.append(f"candidate missing sub-line '{member}'")

    target_norm = normalize(product_name)
    cand_norm = normalize(candidate_name)
    if 'gentle' in target_norm and 'oily' in cand_norm and 'oily' not in target_norm:
        reasons.append('skin type mismatch: gentle vs oily')
    if 'oily' in target_norm and 'gentle' in cand_norm and 'gentle' not in target_norm:
        reasons.append('skin type mismatch: oily vs gentle')

    if 'relief sun' in target_norm and 'aqua fresh' in cand_norm:
        reasons.append('variant mismatch: relief sun vs aqua fresh')
    if 'aqua fresh' in target_norm and 'relief sun' in cand_norm and 'aqua fresh' not in cand_norm:
        reasons.append('variant mismatch: aqua fresh vs relief sun')

    c_compact = compact(candidate_name)
    markers = critical_markers(product_name, target_size)
    missing_markers = sorted(marker for marker in markers if compact(marker) not in c_compact)
    if missing_markers:
        reasons.append(f'missing critical markers: {missing_markers}')
    candidate_marker_size = primary_size(candidate_name)
    candidate_markers = critical_markers(candidate_name, candidate_marker_size)
    unexpected_markers = sorted(candidate_markers - markers)
    target_words = set(normalize(product_name).split())
    candidate_words = set(normalize(candidate_name).split())
    unexpected_shade_words = (candidate_words & SHADE_TOKENS) - (target_words & SHADE_TOKENS)
    unexpected_variant_marker = target_type in VARIANT_TYPES and bool(unexpected_shade_words)
    if unexpected_markers:
        if target_type != 'sunscreen' and any(m.startswith('spf') for m in unexpected_markers):
            reasons.append(f'unexpected SPF marker on non-sunscreen: {sorted(unexpected_markers)}')
        elif markers or unexpected_variant_marker:
            reasons.append(f'unexpected critical markers: {sorted(unexpected_markers)}')

    variants = variant_tokens(brand, product_name, target_size)
    c_tokens = set(normalize(candidate_name).split())
    missing_variants = sorted(token for token in variants if token not in c_tokens and compact(token) not in c_compact)
    if missing_variants:
        reasons.append(f'variant mismatch: {missing_variants}')

    target_tokens = significant_tokens(brand, product_name, target_size)
    matched_tokens = {
        target_token
        for target_token in target_tokens
        if any(
            target_token == candidate_token or fuzz.ratio(target_token, candidate_token) >= 88
            for candidate_token in c_tokens
        )
    }
    coverage = len(matched_tokens) / len(target_tokens) if target_tokens else 1.0
    similarity = fuzz.token_set_ratio(normalize(product_name), normalize(candidate_name)) / 100.0
    score = round((coverage * 0.68 + similarity * 0.32) * 100, 2)
    if coverage < 0.66 and similarity < 0.90:
        reasons.append(f'name coverage too low ({coverage:.2f}, similarity {similarity:.2f})')
    if score < 65:
        reasons.append(f'match score below threshold ({score:.2f} < 65.00)')

    return MatchResult(not reasons, score, reasons)
