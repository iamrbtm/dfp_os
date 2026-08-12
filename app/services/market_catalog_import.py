from __future__ import annotations

import base64
import json
import re
from datetime import date, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from app.config import BASE_DIR
from app.extensions import db
from app.models import MarketCategory
from app.services.ai_gateway import get_openai_compatible_client, model_for
from app.services.business import get_default_business


MARKET_CATALOG_EXTRACTION_SCHEMA_PATH = (
    BASE_DIR / "import" / "validate" / "MarketCatalogExtraction.schema"
)
FETCHED_URL_TEXT_LIMIT = 18_000
MARKET_CATALOG_AI_TIMEOUT_SECONDS = 60

MARKET_CATALOG_AI_PROMPT = """You are an extraction + light-research agent for Dude Fish Printing, a small
3D-printing business in Clarksville, Tennessee. You are populating an internal
"market catalog" of vendor/farmer/craft markets we may want to attend.

The user will hand you ONE input that can be any of:
  - an image (flyer, screenshot, poster photo)
  - raw HTML from a website
  - a URL (the server may have fetched the page text for you)
  - plain text / pasted notes

The server may include fetched URL content as context when the user gives a URL.
Use the original input and any fetched context. You are responsible for reading,
parsing, and light research from that context.

You do not have browser tools in this chat call. Do not say you need to fetch
another page or continue researching. Return best-effort JSON from the provided
context, with null for missing fields and notes telling the human what to verify.

============================================================
YOUR TOOL BUDGET (hard caps -- do not exceed)
============================================================
  - Web searches: 0
  - Page fetches: 0
  - Total tool calls: 0

Use them wisely. Prioritize in this order:
  1. Read the original input and any fetched source text thoroughly.
  2. Extract only what is present or clearly implied.
  3. For missing application fees, rules, load-in times, insurance requirements,
     or organizer details, use null and add a specific human-review note.
  4. Stop. Do not loop. Commit to a final JSON object.

============================================================
OUTPUT RULES
============================================================
1. Output EXACTLY ONE JSON object. No prose, no markdown, no fences. Your
   response must be parseable by `json.loads`.

2. If a field cannot be determined after exhausting your tool budget, use
   `null`. Never invent data. Never use "" for a missing string.

3. Format normalization:
   - Times: 24-hour "HH:MM" (e.g. "09:00", "17:30"). Convert "9am-5pm".
   - Dates: ISO "YYYY-MM-DD".
   - State: 2-letter US code, uppercase (e.g. "TN").
   - Country: default "US" when address is US-shaped.
   - Prices: numbers only, USD, no "$" (e.g. 75.00).
   - URLs: absolute, must start with http:// or https://.
   - Phone: digits + optional + - . ( ) spaces. No invented extensions.
   - Booleans: true ONLY when source explicitly says so. Default false.

4. Recurrence:
   - `is_recurring` = true only for repeating schedules.
   - One-off events: put the date in BOTH `anchor_date` and
     `next_occurrence_date`.
   - Recurring events: `anchor_date` = next upcoming known date (or first
     known occurrence). `recurrence_description` is a short human label
     like "Every Saturday" or "First Saturday each month, May-October".
   - Only set `rrule` if you can confidently produce an iCalendar RRULE.
     Otherwise leave null; the app's recurrence service will build one.

5. Booth tiers: one entry per distinct size/price option, ordered cheapest
   first (or by source order via `sort_order`). If only one price is given
   with no tiers, emit a single tier with `label: "Standard"`.

6. Amenities default to false. Flip to true only if the source explicitly
   states availability.

7. `interest_level` is an internal Dude Fish field. You cannot know it.
   ALWAYS emit "watching". A human will review.

8. `category_hint`: one of these slugs or null. Do not invent new slugs.
   ["farmers_market", "craft_market", "holiday_market", "antique_fair",
    "food_festival", "art_walk", "pop_up", "vendor_expo", "other"]

9. `extraction_notes`: write 1-3 sentences explaining what you researched,
   what you guessed, and what the human reviewer should double-check. Be
   specific. Example: "Fetched application page at https://... -- found
   booth fee $75 not on flyer. Organizer email not posted anywhere;
   inferred from Facebook page."

10. `sources_consulted`: list every URL you actually fetched or saw content
    from, in order. This is for audit. Include the original input URL if
    the user gave you one.

11. `search_queries_used`: list every search query you issued. Audit trail.

12. `research_complete`: true if you used your full budget OR if you are
    satisfied you cannot get more useful info. false only if you hit a
    transient error and want a human to retry. Almost always true.

13. `field_confidence`: per group, "high" = explicit in source, "medium" =
    clearly implied, "low" = inference. Be honest.

14. Your final JSON must validate against the MarketCatalogExtraction schema.json
    Coerce bad values to the closest valid value and note it in
    extraction_notes.

input: <input data goes here>"""


_CATEGORY_HINTS = {
    "farmers_market": ("farmers", "farmers-market", "farmers market"),
    "craft_market": ("craft", "craft-market", "craft market"),
    "holiday_market": ("holiday", "holiday-market", "holiday market"),
    "antique_fair": ("antique-vintage", "antique", "antique fair"),
    "food_festival": ("festival", "food festival"),
    "art_walk": ("art", "art walk"),
    "pop_up": ("pop-up", "pop up", "popup"),
    "vendor_expo": ("trade-show", "vendor expo", "expo"),
    "other": ("other",),
}


def load_market_catalog_extraction_schema() -> dict[str, Any]:
    with MARKET_CATALOG_EXTRACTION_SCHEMA_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def generate_market_catalog_extraction(
    *, user_input: str | None, uploaded_file=None
) -> dict[str, Any]:
    schema = load_market_catalog_extraction_schema()
    content: list[dict[str, Any]] = [
        {"type": "text", "text": MARKET_CATALOG_AI_PROMPT.replace("<input data goes here>", "")},
        {
            "type": "text",
            "text": "MarketCatalogExtraction.schema.json:\n" + json.dumps(schema),
        },
    ]
    text_input = (user_input or "").strip()
    if text_input:
        content.append({"type": "text", "text": f"input: {text_input}"})
        url = _extract_url(text_input)
        fetched = _fetch_url_context(text_input)
        if fetched:
            content.append({"type": "text", "text": fetched})
            direct_payload = _extract_market_from_text(url=url, source_text=fetched)
            if direct_payload:
                return direct_payload

    if uploaded_file and uploaded_file.filename:
        file_content = uploaded_file.read()
        content_type = uploaded_file.mimetype or "application/octet-stream"
        if content_type.startswith("image/"):
            encoded = base64.b64encode(file_content).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{content_type};base64,{encoded}"},
                }
            )
        else:
            content.append(
                {
                    "type": "text",
                    "text": _decode_uploaded_file(
                        uploaded_file.filename, content_type, file_content
                    ),
                }
            )

    client = get_openai_compatible_client().with_options(timeout=MARKET_CATALOG_AI_TIMEOUT_SECONDS)
    try:
        response = client.chat.completions.create(
            model=model_for("market_catalog"),
            messages=[{"role": "user", "content": content}],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        if "timed out" in str(exc).lower() or exc.__class__.__name__ == "APITimeoutError":
            raise ValueError(
                "AI provider timed out while extracting this market. Try a faster model or paste the event details directly."
            ) from exc
        raise
    raw_content = response.choices[0].message.content or ""
    payload = _parse_ai_json(raw_content)
    if not isinstance(payload, dict) or not payload.get("name"):
        raise ValueError("AI response did not contain a usable market catalog extraction.")
    return payload


def _fetch_url_context(value: str) -> str | None:
    url = _extract_url(value)
    if not url:
        return None
    try:
        response = requests.get(
            url,
            timeout=12,
            headers={"User-Agent": "Dude Fish OS market catalog importer/1.0"},
        )
        response.raise_for_status()
    except requests.RequestException:
        return f"Original input URL could not be fetched by the server: {url}"
    content_type = response.headers.get("content-type", "")
    text = _html_to_readable_text(response.text)[:FETCHED_URL_TEXT_LIMIT]
    return f"Fetched source URL: {url}\nContent-Type: {content_type}\n\n{text}"


def _html_to_readable_text(source: str) -> str:
    soup = BeautifulSoup(source, "html.parser")
    for element in soup(["script", "style", "svg", "noscript", "template"]):
        element.decompose()
    return "\n".join(
        line for line in (text.strip() for text in soup.get_text("\n").splitlines()) if line
    )


def _extract_market_from_text(*, url: str | None, source_text: str) -> dict[str, Any] | None:
    text = source_text.strip()
    name = _first_content_line(text)
    if not name:
        return None
    address = _address_from_text(text)
    event_date = _first_event_date(text)
    email = _email_from_text(text)
    if not address and not event_date and not email:
        return None

    city = state = zip_code = None
    if address:
        city_match = re.search(r"\n([^\n,]+),?\s+([A-Z]{2})\s+(\d{5})(?:-\d{4})?", text)
        if city_match:
            city = city_match.group(1).strip()
            state = city_match.group(2)
            zip_code = city_match.group(3)

    vendor_count = _first_int_match(text, r"(?:over\s+)?(\d{2,4})\s+local vendors")
    application_url = (
        _absolute_url(url, "/vendor-applications/")
        if "vendor applications" in text.lower()
        else None
    )
    full_categories = _section_after(
        text, "Full Categories:", stop_markers=("All vendors", "Venue Information")
    )
    what_to_expect = _section_after(text, "What to Expect", stop_markers=("Location",))
    notes = "Fast URL extraction from fetched page text. Human should verify booth fees, load-in details, and application requirements."
    if full_categories:
        notes += f" Full categories listed: {full_categories}"

    return {
        "name": name,
        "website_url": url,
        "description": what_to_expect,
        "interest_level": "watching",
        "location": {
            "location_name": "Covered pavilion" if "covered pavilion" in text.lower() else None,
            "address": address,
            "city": city,
            "state": state,
            "zip_code": zip_code,
            "country": "US" if state else None,
        },
        "timing": {
            "timezone": "America/Chicago",
            "is_recurring": False,
            "anchor_date": event_date.isoformat() if event_date else None,
            "next_occurrence_date": event_date.isoformat() if event_date else None,
        },
        "scale": {"estimated_vendor_count": vendor_count, "estimated_attendee_count": None},
        "amenities": {
            "power_available": False,
            "wifi_available": False,
            "food_available": False,
            "restrooms_available": False,
            "indoor": False,
            "covered_outdoor": "covered pavilion" in text.lower(),
            "outdoor": "outdoor event" in text.lower(),
            "parking_notes": "FREE parking available onsite."
            if "free parking" in text.lower()
            else None,
        },
        "organizer": {
            "name": name,
            "email": email,
            "phone": None,
            "application_url": application_url,
            "application_contact": None,
            "application_deadline_description": "Rolling acceptance of vendors."
            if "rolling acceptance" in text.lower()
            else None,
        },
        "rules": {
            "booth_rules": "Only trained service animals allowed in the event area."
            if "trained service animals" in text.lower()
            else None,
            "required_documents": None,
        },
        "booth_tiers": [],
        "category_hint": "holiday_market" if "christmas" in text.lower() else None,
        "field_confidence": {
            "identity": "high",
            "location": "high" if address else "low",
            "timing": "medium" if event_date else "low",
            "scale": "high" if vendor_count else "low",
            "amenities": "medium",
            "organizer": "medium" if email else "low",
            "rules": "medium",
            "booth_tiers": "low",
        },
        "sources_consulted": [
            {"url": url, "purpose": "Fetched source page", "fields_filled": ["market catalog"]}
        ]
        if url
        else [],
        "search_queries_used": [],
        "research_complete": True,
        "extraction_notes": notes,
    }


def _first_content_line(text: str) -> str | None:
    for line in text.splitlines():
        cleaned = line.strip(" -")
        if cleaned and not cleaned.lower().startswith(
            ("fetched source url", "content-type", "skip to")
        ):
            return cleaned.split(" – ", 1)[0].strip()[:200]
    return None


def _address_from_text(text: str) -> str | None:
    match = re.search(
        r"\n(\d{3,6}\s+[^\n]+(?:Road|Rd|Street|St|Avenue|Ave|Drive|Dr|Lane|Ln))\n", text
    )
    return match.group(1).strip() if match else None


def _first_event_date(text: str) -> date | None:
    year_match = re.search(r"\b(20\d{2})\b", text)
    year = int(year_match.group(1)) if year_match else date.today().year
    month_names = (
        "January|February|March|April|May|June|July|August|September|October|November|December"
    )
    match = re.search(
        rf"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?\s*({month_names})\s+(\d{{1,2}})\b",
        text,
    )
    if not match:
        return None
    month = {
        name: index
        for index, name in enumerate(
            "January February March April May June July August September October November December".split(),
            start=1,
        )
    }[match.group(1)]
    return date(year, month, int(match.group(2)))


def _email_from_text(text: str) -> str | None:
    match = re.search(r"[A-Z0-9._%+-]+\s*@\s*[A-Z0-9.-]+\.[A-Z]{2,}", text, re.IGNORECASE)
    return re.sub(r"\s+", "", match.group(0)) if match else None


def _first_int_match(text: str, pattern: str) -> int | None:
    match = re.search(pattern, text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _section_after(text: str, marker: str, *, stop_markers: tuple[str, ...]) -> str | None:
    if marker not in text:
        return None
    section = text.split(marker, 1)[1]
    for stop in stop_markers:
        if stop in section:
            section = section.split(stop, 1)[0]
    section = " ".join(line.strip() for line in section.splitlines() if line.strip())
    return section[:800] or None


def _absolute_url(base_url: str | None, path: str) -> str | None:
    if not base_url:
        return None
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def _extract_url(value: str) -> str | None:
    match = re.search(r"https?://[^\s<>'\"]+", value.strip())
    if not match:
        return None
    url = match.group(0).rstrip(".,);]")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return url


def _parse_ai_json(raw_content: str) -> dict[str, Any]:
    content = raw_content.strip()
    if not content:
        raise ValueError(
            "AI provider returned an empty response. Try a different model or paste event text instead of only a URL."
        )
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content).strip()
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        content = content[start : end + 1]
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        preview = raw_content.strip().replace("\n", " ")[:180] or "empty response"
        raise ValueError(f"AI provider returned non-JSON output: {preview}") from exc
    if not isinstance(payload, dict):
        raise ValueError("AI provider returned JSON, but it was not an object.")
    return payload


def extraction_to_listing_fields(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    location = payload.get("location") or {}
    timing = payload.get("timing") or {}
    scale = payload.get("scale") or {}
    amenities = payload.get("amenities") or {}
    organizer = payload.get("organizer") or {}
    rules = payload.get("rules") or {}
    business = get_default_business()

    fields = {
        "name": _required_string(payload.get("name"), "Imported market"),
        "category_id": _category_id_for_hint(payload.get("category_hint")),
        "description": _clean(payload.get("description")),
        "website_url": _clean(payload.get("website_url")),
        "location_name": _clean(location.get("location_name")),
        "address": _clean(location.get("address")),
        "city": _clean(location.get("city")),
        "state": _clean(location.get("state")),
        "zip_code": _clean(location.get("zip_code")),
        "latitude": _float_or_none(location.get("latitude")),
        "longitude": _float_or_none(location.get("longitude")),
        "default_start_time": _parse_time(timing.get("default_start_time")),
        "default_end_time": _parse_time(timing.get("default_end_time")),
        "timezone": _clean(timing.get("timezone")) or "America/Chicago",
        "is_recurring": bool(timing.get("is_recurring")),
        "rrule": _clean(timing.get("rrule")),
        "recurrence_description": _clean(timing.get("recurrence_description")),
        "anchor_date": _parse_date(timing.get("anchor_date")),
        "estimated_vendor_count": _int_or_none(scale.get("estimated_vendor_count")),
        "estimated_attendee_count": _int_or_none(scale.get("estimated_attendee_count")),
        "power_available": bool(amenities.get("power_available")),
        "wifi_available": bool(amenities.get("wifi_available")),
        "food_available": bool(amenities.get("food_available")),
        "restrooms_available": bool(amenities.get("restrooms_available")),
        "indoor": bool(amenities.get("indoor")),
        "covered_outdoor": bool(amenities.get("covered_outdoor")),
        "outdoor": bool(amenities.get("outdoor")),
        "parking_notes": _clean(amenities.get("parking_notes")),
        "organizer_name": _clean(organizer.get("name")),
        "organizer_email": _clean(organizer.get("email")),
        "organizer_phone": _clean(organizer.get("phone")),
        "application_url": _clean(organizer.get("application_url")),
        "application_contact": _clean(organizer.get("application_contact")),
        "application_deadline_description": _clean(
            organizer.get("application_deadline_description")
        ),
        "booth_rules": _clean(rules.get("booth_rules")),
        "required_documents": _clean(rules.get("required_documents")),
        "notes": _import_notes(payload),
        "interest_level": payload.get("interest_level") or "watching",
        "business_id": business.id if business else None,
    }
    next_occurrence = _parse_date(timing.get("next_occurrence_date"))
    if next_occurrence and not fields["anchor_date"]:
        fields["anchor_date"] = next_occurrence

    tiers = [
        _tier_fields(tier, index) for index, tier in enumerate(payload.get("booth_tiers") or [])
    ]
    return fields, tiers


def _decode_uploaded_file(filename: str, content_type: str, content: bytes) -> str:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = ""
    if not text:
        return (
            f"Uploaded file: {filename} ({content_type}). The file could not be decoded as UTF-8; "
            "extract only from any other provided input."
        )
    return f"Uploaded file: {filename} ({content_type})\n\n{text}"


def _category_id_for_hint(hint: str | None) -> int | None:
    aliases = _CATEGORY_HINTS.get(hint or "", ())
    if not aliases:
        return None
    normalized = {alias.lower() for alias in aliases}
    categories = db.session.query(MarketCategory).filter(MarketCategory.deleted_at.is_(None)).all()
    for category in categories:
        if category.slug.lower() in normalized or category.name.lower() in normalized:
            return category.id
    return None


def _import_notes(payload: dict[str, Any]) -> str | None:
    parts = []
    if payload.get("notes"):
        parts.append(str(payload["notes"]).strip())
    if payload.get("extraction_notes"):
        parts.append(f"AI extraction notes: {str(payload['extraction_notes']).strip()}")
    if payload.get("field_confidence"):
        parts.append(f"Field confidence: {json.dumps(payload['field_confidence'], sort_keys=True)}")
    sources = payload.get("sources_consulted") or []
    if sources:
        urls = [
            source.get("url")
            for source in sources
            if isinstance(source, dict) and source.get("url")
        ]
        if urls:
            parts.append("Sources consulted: " + "; ".join(urls))
    searches = payload.get("search_queries_used") or []
    if searches:
        parts.append("Search queries used: " + "; ".join(str(item) for item in searches))
    if "research_complete" in payload:
        parts.append(f"Research complete: {bool(payload['research_complete'])}")
    return "\n\n".join(part for part in parts if part) or None


def _tier_fields(tier: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "label": _required_string(tier.get("label"), "Standard"),
        "dimensions": _clean(tier.get("dimensions")),
        "price": _decimal_or_none(tier.get("price")),
        "corner_premium": _decimal_or_none(tier.get("corner_premium")),
        "notes": _clean(tier.get("notes")),
        "sort_order": _int_or_none(tier.get("sort_order")) or index,
    }


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_string(value: Any, fallback: str) -> str:
    return _clean(value) or fallback


def _parse_date(value: Any) -> date | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _parse_time(value: Any) -> time | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return time.fromisoformat(text)
    except ValueError:
        return None


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation, ValueError:
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except TypeError, ValueError:
        return None


def schema_file_exists() -> bool:
    return Path(MARKET_CATALOG_EXTRACTION_SCHEMA_PATH).exists()
