from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.services.market_catalog_importers.util import _normalize_key, extract_county

TENNESSEE_FAIRS_CALENDAR_URL = "https://tennesseefairs.com/calendar/"
TENNESSEE_FAIRS_DIRECTORY_URL = "https://tennesseefairs.com/directory/"

# Importer metadata (surfaced in the import modal + schema source envelope).
KEY = "tennesseefairs"
NAME = "Tennessee Fairs"
DESCRIPTION = (
    "Scrape tennesseefairs.com calendar + directory and import county/regional "
    "fairs into the Market Catalog."
)
SOURCE_URLS = [TENNESSEE_FAIRS_CALENDAR_URL, TENNESSEE_FAIRS_DIRECTORY_URL]

_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|November|December"
)
_CLASSIFICATION_RE = re.compile(r"^\(([EMW])\)\s+([A-Za-z0-9+/ ]+)\s*$")
_DASH_RE = re.compile(r"^-{3,}\s*$")
_FAIR_LINK_RE = re.compile(r"^\[(.+?)\]\((https?://[^)]+)\)\s*$")
_WEBSITE_RE = re.compile(r"^\[Website\]\((https?://[^)]+)\)\s*$")
_ADDRESS_WORD_RE = re.compile(
    r"\b(ROAD|DRIVE|STREET|AVENUE|LANE|BOULEVARD|BLVD|RD|DR|ST|AVE|LN|"
    r"HIGHWAY|HWY|PKWY|PIKE|COURT|CT|WAY|WY|BOX)\b",
    re.I,
)
_PHONE_RE = re.compile(r"\(\d{3}\)\s*\d{3}-\d{4}|\d{3}-\d{3}-\d{4}")
_DATE_RE = re.compile(rf"\b({_MONTHS})\b.*?\b(\d{{1,2}})(?:\s*-\s*\d{{1,2}})?", re.I)
_DATE_WITH_YEAR_RE = re.compile(
    rf"\b({_MONTHS})\s+(\d{{1,2}})\s*[-–]\s*\d{{1,2}},?\s*(\d{{4}})\b", re.I
)


def _strip_bullet(line: str) -> str:
    return re.sub(r"^\*\s+", "", line).strip()


def _extract_email(item: str) -> str | None:
    m = re.match(r"^\[([^\]]+)\]\(mailto:[^)]*\)", item)
    if m:
        return m.group(1).strip().lstrip("%").strip() or None
    if re.match(r"^[\w.+-]+@[\w.-]+\.\w+$", item):
        return item.strip()
    return None


def _parse_address(text: str | None) -> tuple[str | None, str | None, str | None]:
    if not text:
        return None, None, None
    m = re.search(r"([^,]+),\s*([A-Za-z]{2})\s+(\d{5})", text)
    if not m:
        return None, None, None
    return m.group(1).strip().title(), m.group(2).upper(), m.group(3)


def _MONTH_INDEX(name: str) -> int | None:
    months = [
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
    ]
    try:
        return months.index(name.lower()) + 1
    except ValueError:
        return None


def _parse_date(text: str | None) -> date | None:
    if not text:
        return None
    m = _DATE_WITH_YEAR_RE.search(text)
    if m:
        month = _MONTH_INDEX(m.group(1))
        if month:
            try:
                return date(int(m.group(3)), month, int(m.group(2)))
            except ValueError:
                return None
    return None


def parse_calendar(markdown: str) -> list[dict[str, Any]]:
    """Parse tennesseefairs.com/calendar: each fair is a link heading (the event
    URL) followed by date + address bullets. Skips blank lines before underlines.
    """
    entries: list[dict[str, Any]] = []
    lines = markdown.splitlines()
    n = len(lines)
    i = 0
    while i < n:
        line = lines[i].rstrip()
        m = _FAIR_LINK_RE.match(line)
        if m:
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            if j < n and _DASH_RE.match(lines[j].strip()):
                name = m.group(1).strip()
                url = m.group(2).strip()
                details: list[str] = []
                k = j + 1
                while k < n:
                    bl = lines[k].strip()
                    if not bl:
                        k += 1
                        continue
                    if bl.startswith("!["):
                        k += 1
                        continue
                    if _FAIR_LINK_RE.match(bl):
                        break
                    if _DASH_RE.match(bl):
                        break
                    if bl.startswith("*"):
                        details.append(_strip_bullet(bl))
                    k += 1
                date_text = details[0] if len(details) >= 1 else None
                address_text = details[1] if len(details) >= 2 else None
                city, state, zip_code = _parse_address(address_text)
                entries.append(
                    {
                        "name": name,
                        "event_url": url,
                        "calendar_date_text": date_text,
                        "address_text": address_text,
                        "city": city,
                        "state": state,
                        "zip": zip_code,
                    }
                )
                i = k
                continue
        i += 1
    return entries


def parse_directory(markdown: str) -> list[dict[str, Any]]:
    """Parse tennesseefairs.com/directory: each fair is an underlined heading with
    a ``(E)/(M)/(W) AAA`` classification, contact bullets, a blank line, then
    event bullets (dates, fairgrounds address, carnival), then a [Website] link.
    """
    entries: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    phase: str = "contact"
    lines = markdown.splitlines()
    n = len(lines)
    i = 0
    while i < n:
        s = lines[i].strip()
        if not s:
            # Only advance to the event block once contact details have appeared;
            # a blank line right after the classification underline must not flip.
            if cur is not None and phase == "contact" and (
                cur["contact_name"] or cur["email"] or cur["phone"] or cur["contact_address"]
            ):
                phase = "event"
            i += 1
            continue

        if not s.startswith("*") and not s.startswith("![") and not s.startswith("["):
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            if j < n and _DASH_RE.match(lines[j].strip()):
                heading = s
                class_match = _CLASSIFICATION_RE.match(heading)
                if class_match:
                    if cur is not None:
                        cur["classification"] = heading.strip()
                    i = j + 1
                    continue
                if cur is not None:
                    entries.append(cur)
                cur = {
                    "name": heading.strip(),
                    "classification": None,
                    "contact_name": None,
                    "contact_address": None,
                    "phone": None,
                    "email": None,
                    "date_text": None,
                    "fairgrounds_address": None,
                    "carnival": None,
                    "website_url": None,
                }
                phase = "contact"
                i = j + 1
                continue

        if s.startswith("*") and cur is not None:
            item = _strip_bullet(s)
            email = _extract_email(item)
            if email:
                cur["email"] = email
            elif _PHONE_RE.search(item):
                cur["phone"] = item
            elif _ADDRESS_WORD_RE.search(item) and re.search(r"\bTN\b", item.upper()):
                if phase == "event" or cur["contact_address"] is not None:
                    cur["fairgrounds_address"] = item
                else:
                    cur["contact_address"] = item
            elif phase == "event" and _DATE_RE.search(item):
                cur["date_text"] = item
            elif phase == "contact" and cur["contact_name"] is None:
                cur["contact_name"] = item
            else:
                cur["carnival"] = (cur["carnival"] + " " + item).strip() if cur["carnival"] else item
            i += 1
            continue

        wm = _WEBSITE_RE.match(s)
        if wm and cur is not None:
            cur["website_url"] = wm.group(1)
        i += 1

    if cur is not None:
        entries.append(cur)
    return [e for e in entries if _directory_entry_has_signal(e)]


def _directory_entry_has_signal(entry: dict[str, Any]) -> bool:
    """Drop page-title headings (e.g. 'Tennessee Fairs') that carry no fair data."""
    return any(
        entry.get(k)
        for k in (
            "website_url",
            "contact_name",
            "email",
            "phone",
            "date_text",
            "fairgrounds_address",
            "contact_address",
            "carnival",
        )
    )


def merge_records(
    calendar_list: list[dict[str, Any]], directory_list: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Join calendar + directory entries by fair name (county-keyed).

    Directory entries are the base (richer contact data), enriched with the
    calendar event link and any missing location fields. Calendar-only fairs are
    appended as their own records.
    """
    dir_by_key = {_normalize_key(d["name"]): d for d in directory_list}
    cal_by_key = {_normalize_key(c["name"]): c for c in calendar_list}
    records: list[dict[str, Any]] = []

    for d in directory_list:
        rec = dict(d)
        key = _normalize_key(d["name"])
        cal = cal_by_key.get(key)
        if cal:
            rec["event_url"] = cal.get("event_url")
            rec["calendar_date_text"] = cal.get("calendar_date_text")
            rec["source"] = "directory+calendar"
            if not rec.get("fairgrounds_address") and cal.get("address_text"):
                rec["fairgrounds_address"] = cal["address_text"]
            rec["city"] = rec.get("city") or cal.get("city")
            rec["state"] = rec.get("state") or cal.get("state")
            rec["zip"] = rec.get("zip") or cal.get("zip")
        else:
            rec["event_url"] = None
            rec["calendar_date_text"] = None
            rec["source"] = "directory"
        records.append(rec)

    for c in calendar_list:
        if _normalize_key(c["name"]) not in dir_by_key:
            rec = dict(c)
            rec.setdefault("classification", None)
            rec.setdefault("contact_name", None)
            rec.setdefault("contact_address", None)
            rec.setdefault("phone", None)
            rec.setdefault("email", None)
            rec.setdefault("date_text", None)
            rec.setdefault("fairgrounds_address", c.get("address_text"))
            rec.setdefault("carnival", None)
            rec.setdefault("website_url", None)
            rec["source"] = "calendar"
            records.append(rec)

    return records


def fetch_pages(client) -> dict[str, str]:
    """Site-owned fetch: scrape each source URL via the shared Firecrawl client."""
    return {url: client.scrape_markdown(url) for url in SOURCE_URLS}


def parse_pages(pages: dict[str, str]) -> dict[str, Any]:
    """Site entry point used by the shared runner.

    Returns merged records plus per-source counts for the import summary.
    """
    cal = parse_calendar(pages.get(TENNESSEE_FAIRS_CALENDAR_URL, ""))
    dire = parse_directory(pages.get(TENNESSEE_FAIRS_DIRECTORY_URL, ""))
    return {
        "records": merge_records(cal, dire),
        "counts": {"calendar": len(cal), "directory": len(dire)},
    }


def build_payload(record: dict[str, Any]) -> dict[str, Any]:
    """Map a merged fair record into one MarketCatalogImport entry."""
    name = record["name"]
    website = record.get("event_url") or record.get("website_url")
    classification = record.get("classification")
    region = None
    if classification:
        cm = _CLASSIFICATION_RE.match(classification)
        if cm:
            region = {"E": "East", "M": "Middle", "W": "West"}.get(cm.group(1))

    address = record.get("fairgrounds_address") or record.get("contact_address") or record.get("address_text")
    city = record.get("city")
    state = record.get("state") or "TN"
    zip_code = record.get("zip")
    date_text = record.get("date_text") or record.get("calendar_date_text")
    anchor = _parse_date(date_text)

    desc_parts: list[str] = []
    if region:
        desc_parts.append(f"{region} Tennessee fair")
    if classification:
        desc_parts.append(f"TFAI classification: {classification}")
    description = "; ".join(desc_parts) or None

    notes: list[str] = []
    notes.append("Imported from tennesseefairs.com calendar + directory via Firecrawl.")
    has_cal = bool(record.get("event_url"))
    has_dir = record.get("source", "").startswith("directory") or bool(record.get("contact_name"))
    notes.append(f"Source pages: calendar={'yes' if has_cal else 'no'}, directory={'yes' if has_dir else 'no'}.")
    county = extract_county(name)
    if county:
        notes.append(f"County: {county}.")
    if record.get("carnival"):
        notes.append(f"Carnival/midway: {record['carnival']}")

    return {
        "name": name,
        "website_url": website,
        "description": description,
        "interest_level": "watching",
        "location": {
            "address": address,
            "city": city,
            "state": state,
            "zip_code": zip_code,
        },
        "timing": {
            "timezone": "America/Chicago",
            "is_recurring": True,
            "recurrence_description": "Annual county fair (yearly)",
            "anchor_date": anchor.isoformat() if anchor else None,
            "next_occurrence_date": anchor.isoformat() if anchor else None,
        },
        "scale": {},
        "amenities": {},
        "organizer": {
            "name": record.get("contact_name"),
            "email": record.get("email"),
            "phone": record.get("phone"),
        },
        "rules": {},
        "notes": " ".join(notes),
    }
