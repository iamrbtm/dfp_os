from __future__ import annotations

import os

from marshmallow import EXCLUDE, Schema, fields, validate

SCHEMA_VERSION = "2.0.0"

_JSON_SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "json_schema.json"
)


class LocationSchema(Schema):
    location_name = fields.String(load_default=None)
    address = fields.String(load_default=None)
    city = fields.String(load_default=None)
    state = fields.String(load_default=None)
    zip_code = fields.String(load_default=None)
    latitude = fields.Float(load_default=None)
    longitude = fields.Float(load_default=None)


class TimingSchema(Schema):
    default_start_time = fields.String(load_default=None)
    default_end_time = fields.String(load_default=None)
    timezone = fields.String(load_default=None)
    is_recurring = fields.Boolean(load_default=None)
    rrule = fields.String(load_default=None)
    recurrence_description = fields.String(load_default=None)
    anchor_date = fields.Date(load_default=None)
    next_occurrence_date = fields.Date(load_default=None)


class ScaleSchema(Schema):
    estimated_vendor_count = fields.Integer(load_default=None, validate=validate.Range(min=0))
    estimated_attendee_count = fields.Integer(load_default=None, validate=validate.Range(min=0))


class AmenitiesSchema(Schema):
    power_available = fields.Boolean(load_default=None)
    wifi_available = fields.Boolean(load_default=None)
    food_available = fields.Boolean(load_default=None)
    restrooms_available = fields.Boolean(load_default=None)
    indoor = fields.Boolean(load_default=None)
    covered_outdoor = fields.Boolean(load_default=None)
    outdoor = fields.Boolean(load_default=None)
    parking_notes = fields.String(load_default=None)


class OrganizerSchema(Schema):
    name = fields.String(load_default=None)
    email = fields.String(load_default=None)
    phone = fields.String(load_default=None)
    application_url = fields.String(load_default=None)
    application_contact = fields.String(load_default=None)
    application_deadline_description = fields.String(load_default=None)


class RulesSchema(Schema):
    booth_rules = fields.String(load_default=None)
    required_documents = fields.String(load_default=None)


class ImportEntrySchema(Schema):
    """One market/event/fair, mapping to a MarketCatalogListing row."""

    class Meta:
        unknown = EXCLUDE

    name = fields.String(required=True)
    description = fields.String(load_default=None)
    website_url = fields.String(load_default=None)
    interest_level = fields.String(
        load_default=None,
        validate=validate.OneOf(["watching", "interested", "priority"]),
    )
    location = fields.Nested(LocationSchema, load_default=None)
    timing = fields.Nested(TimingSchema, load_default=None)
    scale = fields.Nested(ScaleSchema, load_default=None)
    amenities = fields.Nested(AmenitiesSchema, load_default=None)
    organizer = fields.Nested(OrganizerSchema, load_default=None)
    rules = fields.Nested(RulesSchema, load_default=None)
    notes = fields.String(load_default=None)


class ImportSourceSchema(Schema):
    name = fields.String(load_default=None)
    url = fields.String(required=True)
    page_title = fields.String(load_default=None)
    scraped_at = fields.DateTime(required=True)
    scraper = fields.String(load_default=None)
    query_or_context = fields.String(load_default=None)
    locale = fields.String(load_default=None)


class ImportErrorSchema(Schema):
    message = fields.String(required=True)
    entry_index = fields.Integer(load_default=None)
    field = fields.String(load_default=None)


class MarketCatalogImportSchema(Schema):
    """Universal envelope for any market/event/fair catalog scrape.

    Every importer (one per site) must emit data conforming to this schema so
    downstream mapping into DFPos ``MarketCatalogListing`` stays consistent
    regardless of the source site.
    """

    schema_version = fields.String(required=True, validate=validate.Equal(SCHEMA_VERSION))
    source = fields.Nested(ImportSourceSchema, required=True)
    entries = fields.List(fields.Nested(ImportEntrySchema), required=True)
    errors = fields.List(fields.Nested(ImportErrorSchema), load_default=None)

    class Meta:
        unknown = EXCLUDE


def get_json_schema_path() -> str:
    return _JSON_SCHEMA_PATH


def validate(data: dict, strict: bool = False) -> dict:
    """Validate and normalize a raw scrape dict against the universal schema.

    Returns the deserialized/normalized dict. Raises marshmallow.ValidationError
    on failure. When ``strict`` is True and the optional ``jsonschema`` package
    is installed, also validates against json_schema.json for cross-checking.
    """
    schema = MarketCatalogImportSchema()
    normalized = schema.load(data)

    if strict:
        try:
            import json

            import jsonschema
        except ImportError:
            pass
        else:
            with open(_JSON_SCHEMA_PATH, "r", encoding="utf-8") as fh:
                json_schema = json.load(fh)
            jsonschema.validate(instance=normalized, schema=json_schema)

    return normalized
