from __future__ import annotations

import datetime as dt

import pytest
from marshmallow import ValidationError

from app.schemas.market_catalog_import import validate


def _sample():
    return {
        "schema_version": "2.0.0",
        "source": {
            "name": "Tennessee Fairs",
            "url": "https://tennesseefairs.com/calendar/",
            "scraped_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        },
        "entries": [
            {
                "name": "Clay County Fair",
                "website_url": "https://example.com/clay",
                "description": "East Tennessee fair",
                "interest_level": "watching",
                "location": {"address": "215 Arcot Road", "city": "Celina", "state": "TN", "zip_code": "38551"},
                "timing": {
                    "timezone": "America/Chicago",
                    "is_recurring": True,
                    "anchor_date": "2026-05-26",
                    "next_occurrence_date": "2026-05-26",
                },
                "scale": {"estimated_vendor_count": 40},
                "amenities": {"outdoor": True},
                "organizer": {"name": "Jane Doe", "email": "clay@example.com", "phone": "(931) 555-1234"},
                "rules": {},
                "notes": "Imported via Firecrawl.",
            }
        ],
        "errors": [],
    }


def test_valid_sample_passes():
    out = validate(_sample(), strict=True)
    assert len(out["entries"]) == 1
    assert out["entries"][0]["name"] == "Clay County Fair"


def test_missing_entry_name_is_rejected():
    data = _sample()
    data["entries"][0].pop("name")
    with pytest.raises(ValidationError):
        validate(data)


def test_unknown_interest_level_is_rejected():
    data = _sample()
    data["entries"][0]["interest_level"] = "maybe"
    with pytest.raises(ValidationError):
        validate(data)


def test_wrong_schema_version_is_rejected():
    data = _sample()
    data["schema_version"] = "9.9.9"
    with pytest.raises(ValidationError):
        validate(data)


def test_extra_entry_fields_are_allowed():
    data = _sample()
    data["entries"][0]["category_hint"] = None
    data["entries"][0]["booth_tiers"] = []
    out = validate(data, strict=True)
    assert out["entries"][0]["name"] == "Clay County Fair"
