from __future__ import annotations

import re
from difflib import SequenceMatcher
from enum import StrEnum

from app.models import Product


class MatchConfidence(StrEnum):
    EXACT = "exact"
    FUZZY = "fuzzy"
    SYNONYM = "synonym"
    CATEGORY = "category"
    TAG = "tag"
    WEAK = "weak"


BUSINESS_SYNONYMS: dict[str, list[str]] = {
    "keychain": ["key chain", "key ring", "keyring", "key holder", "key hanger"],
    "magnet": ["magnetic", "refrigerator magnet", "fridge magnet"],
    "ornament": ["decoration", "tree ornament", "holiday decoration", "hanging decoration"],
    "sign": ["nameplate", "plaque", "label", "marker", "plate"],
    "name sign": ["desk sign", "nameplate", "custom name", "name tag", "name plate"],
    "desk sign": ["nameplate", "desk plate", "office sign", "desk nameplate"],
    "teacher gift": ["teacher keychain", "teacher ornament", "teacher appreciation", "teacher sign"],
    "market display": ["vendor sign", "booth sign", "price tag", "tent card", "display stand"],
    "qr sign": ["qr code sign", "qr code display", "qr stand", "qr plate"],
    "fidget": ["fidget toy", "stress toy", "fidget slider", "fidget cube", "pop it"],
    "dragon": ["articulated dragon", "dragon toy", "dragon figure", "dragon model"],
    "flexi": ["flexi animal", "flexi toy", "articulated animal", "flexi figure"],
    "custom name": ["personalized name", "name keychain", "custom keychain", "name tag"],
    "name tag": ["name badge", "label tag", "keychain tag", "luggage tag", "backpack tag"],
    "personalized": ["custom", "monogrammed", "engraved", "made to order"],
    "backpack tag": ["luggage tag", "bag tag", "zipper pull", "bag charm"],
    "coaster": ["drink coaster", "table coaster", "coaster set"],
    "business card": ["card holder", "business card holder", "card case"],
    "phone stand": ["phone holder", "cell stand", "phone dock", "phone prop"],
    "turtle": ["sea turtle", "turtle toy", "tortoise"],
    "axolotl": ["axolotl toy", "axolotl figure", "water dragon"],
    "egg": ["dragon egg", "mystery egg", "dinosaur egg"],
    "slider": ["fidget slider", "stress slider", "slider toy"],
    "holder": ["stand", "organizer", "caddy", "tray"],
    "organizer": ["holder", "caddy", "tray", "storage"],
    "clarksville": ["clarksville tn", "clarksville tennessee", "clarksville gift"],
    "tennessee": ["tn", "tennessee gift", "tennessee souvenir"],
    "military": ["army", "veteran", "military family", "service member"],
    "vendor": ["small business", "booth", "market vendor", "craft fair"],
    "teacher": ["school", "classroom", "educator", "teacher appreciation"],
}


KEYWORD_NORMALIZATIONS = {
    "3d printed ": "",
    "3d print ": "",
    "printed ": "",
    "printable ": "",
    "custom ": "",
    "personalized ": "",
}


DEFAULT_PRODUCT_ALIASES: dict[str, list[str]] = {
    "Rainbow Dragon": ["rainbow dragon", "dragon", "articulated dragon"],
    "Small Articulated Dragon": ["small dragon", "articulated dragon", "mini dragon", "dragon toy"],
    "Mystery Dragon Egg": ["dragon egg", "mystery egg", "egg", "dragon egg surprise"],
    "Fidget Slider": ["fidget", "slider", "fidget toy", "stress slider"],
    "Flexi Turtle": ["turtle", "flexi turtle", "sea turtle", "turtle toy"],
    "Flexi Axolotl": ["axolotl", "flexi axolotl", "axolotl toy", "water dragon"],
    "Clarksville TN Magnet": ["clarksville magnet", "clarksville", "clarksville tn"],
    "Tennessee Ornament": ["tennessee ornament", "tn ornament", "tennessee"],
    "Custom Name Keychain": [
        "custom keychain",
        "name keychain",
        "personalized keychain",
        "keychain",
    ],
    "QR Code Counter Sign": ["qr code sign", "qr sign", "qr code display", "counter sign"],
    "Business Card Holder": ["card holder", "business card", "card stand"],
    "Vendor Price Tag Stand": ["price tag stand", "vendor sign", "tent card", "display stand"],
    "Custom Order Deposit": ["custom order", "deposit", "custom request"],
}


def normalize_product_term(term: str) -> str:
    value = term.strip().lower()
    value = re.sub(r"[^a-z0-9\s\-]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    for prefix, replacement in KEYWORD_NORMALIZATIONS.items():
        if value.startswith(prefix):
            value = value.removeprefix(prefix).strip()
    return re.sub(r"\s+", " ", value).strip()


def find_synonyms(term: str) -> list[str]:
    normalized = normalize_product_term(term)
    results: list[str] = []
    for canonical, syns in BUSINESS_SYNONYMS.items():
        if normalized == canonical or normalized in syns:
            results.append(canonical)
            results.extend(s for s in syns if s != normalized)
    return results


def fuzzy_match_keywords(a: str, b: str, threshold: float = 0.75) -> bool:
    na = normalize_product_term(a)
    nb = normalize_product_term(b)
    if na == nb:
        return True
    if na in nb or nb in na:
        return True
    return SequenceMatcher(None, na, nb).ratio() >= threshold


def _word_overlap(a: str, b: str) -> float:
    words_a = set(normalize_product_term(a).split())
    words_b = set(normalize_product_term(b).split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    return len(intersection) / max(len(words_a), len(words_b))


def match_product_to_term(
    term: str,
    product: Product,
    alias_map: dict[str, list[str]] | None = None,
) -> tuple[bool, MatchConfidence]:
    normalized_term = normalize_product_term(term)
    if not normalized_term:
        return False, MatchConfidence.WEAK

    product_name_normalized = normalize_product_term(product.name)

    if normalized_term == product_name_normalized:
        return True, MatchConfidence.EXACT

    if normalized_term in product_name_normalized or product_name_normalized in normalized_term:
        return True, MatchConfidence.EXACT

    alias_map = alias_map or DEFAULT_PRODUCT_ALIASES
    product_aliases = alias_map.get(product.name, [])
    for alias in product_aliases:
        alias_normalized = normalize_product_term(alias)
        if normalized_term == alias_normalized:
            return True, MatchConfidence.EXACT
        if normalized_term in alias_normalized:
            return True, MatchConfidence.FUZZY

    if fuzzy_match_keywords(normalized_term, product_name_normalized):
        return True, MatchConfidence.FUZZY

    synonyms = find_synonyms(normalized_term)
    for syn in synonyms:
        syn_normalized = normalize_product_term(syn)
        if syn_normalized == product_name_normalized:
            return True, MatchConfidence.SYNONYM
        for alias in product_aliases:
            if syn_normalized == normalize_product_term(alias):
                return True, MatchConfidence.SYNONYM
        if _word_overlap(syn_normalized, product_name_normalized) > 0.5:
            return True, MatchConfidence.SYNONYM

    if product.category and product.category.name:
        cat_normalized = normalize_product_term(product.category.name)
        if normalized_term == cat_normalized or normalized_term in cat_normalized:
            return True, MatchConfidence.CATEGORY

    if product.tags:
        for tag in product.tags.split(","):
            tag_normalized = normalize_product_term(tag.strip())
            if normalized_term == tag_normalized:
                return True, MatchConfidence.TAG

    return False, MatchConfidence.WEAK


def find_matching_products(
    term: str,
    products: list[Product],
    alias_map: dict[str, list[str]] | None = None,
) -> list[tuple[Product, MatchConfidence]]:
    results: list[tuple[Product, MatchConfidence]] = []
    for product in products:
        matches, confidence = match_product_to_term(term, product, alias_map)
        if matches:
            results.append((product, confidence))
    results.sort(
        key=lambda x: (
            {
                MatchConfidence.EXACT: 0,
                MatchConfidence.FUZZY: 1,
                MatchConfidence.SYNONYM: 2,
                MatchConfidence.CATEGORY: 3,
                MatchConfidence.TAG: 4,
                MatchConfidence.WEAK: 5,
            }.get(x[1], 99),
            x[0].name,
        )
    )
    return results


def best_product_match(
    term: str,
    products: list[Product],
    alias_map: dict[str, list[str]] | None = None,
) -> tuple[Product | None, MatchConfidence]:
    matches = find_matching_products(term, products, alias_map)
    if matches:
        return matches[0]
    return None, MatchConfidence.WEAK
