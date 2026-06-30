from __future__ import annotations

import hashlib
import logging
import re
from decimal import Decimal
from typing import Any

from flask import has_request_context, request, session

from app.extensions import db
from app.models import InternalDemandEvent, InternalDemandEventType, Product

logger = logging.getLogger(__name__)

BUYER_INTENT_TERMS = {
    "back to school",
    "birthday",
    "business",
    "classroom",
    "custom",
    "desk",
    "gift",
    "keychain",
    "kids",
    "local",
    "name",
    "ornament",
    "personalized",
    "teacher",
    "vendor",
}

STOP_WORDS = {
    "about",
    "after",
    "again",
    "also",
    "and",
    "are",
    "because",
    "but",
    "can",
    "could",
    "for",
    "from",
    "have",
    "into",
    "like",
    "make",
    "need",
    "please",
    "that",
    "the",
    "this",
    "want",
    "with",
    "would",
    "you",
}


def normalize_keyword(value: str | None) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"[^a-z0-9\s\-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:255]


def extract_terms(text: str | None, *, limit: int = 12) -> list[str]:
    normalized = normalize_keyword(text)
    if not normalized:
        return []

    terms: list[str] = []
    for phrase in sorted(BUYER_INTENT_TERMS, key=len, reverse=True):
        if phrase in normalized and phrase not in terms:
            terms.append(phrase)

    words = [
        word
        for word in normalized.split()
        if len(word) > 2 and word not in STOP_WORDS and not word.isdigit()
    ]
    for index in range(len(words) - 1):
        phrase = f"{words[index]} {words[index + 1]}"
        if phrase not in terms:
            terms.append(phrase)
        if len(terms) >= limit:
            break

    for word in words:
        if word not in terms:
            terms.append(word)
        if len(terms) >= limit:
            break

    return terms[:limit]


def text_fingerprint(text: str | None) -> str | None:
    normalized = normalize_keyword(text)
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _session_key() -> str | None:
    if not has_request_context():
        return None
    key = session.get("_id") or request.cookies.get("session")
    if not key:
        return None
    return hashlib.sha256(str(key).encode("utf-8")).hexdigest()[:32]


def _request_metadata() -> dict[str, Any]:
    if not has_request_context():
        return {}
    return {
        "path": request.path,
        "method": request.method,
        "referrer": request.referrer,
        "user_agent": request.headers.get("User-Agent", "")[:255],
        "remote_addr": request.headers.get("X-Forwarded-For", request.remote_addr or ""),
    }


def record_demand_event(
    event_type: InternalDemandEventType | str,
    *,
    source: str,
    keyword: str | None = None,
    text: str | None = None,
    product: Product | None = None,
    product_id: int | None = None,
    category_id: int | None = None,
    collection_id: int | None = None,
    order_id: int | None = None,
    custom_request_id: int | None = None,
    quantity: int | None = None,
    value: Decimal | str | int | float | None = None,
    metadata: dict[str, Any] | None = None,
    commit: bool = True,
) -> InternalDemandEvent | None:
    try:
        event_enum = (
            event_type
            if isinstance(event_type, InternalDemandEventType)
            else InternalDemandEventType(str(event_type))
        )
        product_id = product_id or (product.id if product else None)
        category_id = category_id or (product.category_id if product else None)
        collection_id = collection_id or (product.collection_id if product else None)
        normalized_keyword = normalize_keyword(
            keyword or (product.name if product else None) or text
        )
        terms = extract_terms(
            " ".join(filter(None, [keyword, product.name if product else None, text]))
        )
        event_metadata = _request_metadata()
        event_metadata.update(metadata or {})

        event = InternalDemandEvent(
            event_type=event_enum,
            source=source,
            keyword=normalized_keyword or None,
            product_id=product_id,
            category_id=category_id,
            collection_id=collection_id,
            order_id=order_id,
            custom_request_id=custom_request_id,
            quantity=quantity,
            value=Decimal(str(value)) if value is not None else None,
            session_key=_session_key(),
            text_fingerprint=text_fingerprint(text or keyword),
            extracted_terms=terms,
            metadata_json=event_metadata or None,
        )
        db.session.add(event)
        if commit:
            db.session.commit()
        return event
    except Exception:
        db.session.rollback()
        logger.exception("Failed to record internal demand event: %s", event_type)
        return None
