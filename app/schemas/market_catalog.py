from __future__ import annotations

from marshmallow import Schema, fields


class MarketCategorySchema(Schema):
    id = fields.Integer(dump_only=True)
    name = fields.String(required=True)
    slug = fields.String(dump_only=True)
    description = fields.String(allow_none=True)
    sort_order = fields.Integer(allow_none=True)
    is_active = fields.Boolean(allow_none=True)
    deleted_at = fields.DateTime(dump_only=True, allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class MarketCatalogBoothTierSchema(Schema):
    id = fields.Integer(dump_only=True)
    listing_id = fields.Integer(dump_only=True)
    label = fields.String(required=True)
    dimensions = fields.String(allow_none=True)
    price = fields.Decimal(as_string=True, allow_none=True)
    corner_premium = fields.Decimal(as_string=True, allow_none=True)
    notes = fields.String(allow_none=True)
    sort_order = fields.Integer(allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class MarketCatalogListingSchema(Schema):
    id = fields.Integer(dump_only=True)
    name = fields.String(required=True)
    slug = fields.String(dump_only=True)
    category_id = fields.Integer(allow_none=True)
    description = fields.String(allow_none=True)
    website_url = fields.String(allow_none=True)
    is_demo = fields.Boolean(dump_only=True)

    location_name = fields.String(allow_none=True)
    address = fields.String(allow_none=True)
    city = fields.String(allow_none=True)
    state = fields.String(allow_none=True)
    zip_code = fields.String(allow_none=True)
    latitude = fields.Float(allow_none=True)
    longitude = fields.Float(allow_none=True)

    default_start_time = fields.String(allow_none=True)
    default_end_time = fields.String(allow_none=True)
    timezone = fields.String(allow_none=True)

    is_recurring = fields.Boolean(allow_none=True)
    rrule = fields.String(allow_none=True)
    recurrence_description = fields.String(allow_none=True)
    next_occurrence_date = fields.Date(dump_only=True, allow_none=True)
    last_occurrence_date = fields.Date(dump_only=True, allow_none=True)
    last_synced_at = fields.DateTime(dump_only=True, allow_none=True)

    estimated_vendor_count = fields.Integer(allow_none=True)
    estimated_attendee_count = fields.Integer(allow_none=True)

    power_available = fields.Boolean(allow_none=True)
    wifi_available = fields.Boolean(allow_none=True)
    food_available = fields.Boolean(allow_none=True)
    restrooms_available = fields.Boolean(allow_none=True)
    indoor = fields.Boolean(allow_none=True)
    covered_outdoor = fields.Boolean(allow_none=True)
    outdoor = fields.Boolean(allow_none=True)
    parking_notes = fields.String(allow_none=True)

    organizer_name = fields.String(allow_none=True)
    organizer_email = fields.String(allow_none=True)
    organizer_phone = fields.String(allow_none=True)
    application_url = fields.String(allow_none=True)
    application_contact = fields.String(allow_none=True)
    application_deadline_description = fields.String(allow_none=True)

    booth_rules = fields.String(allow_none=True)
    required_documents = fields.String(allow_none=True)
    notes = fields.String(allow_none=True)

    interest_level = fields.String(allow_none=True)
    business_id = fields.Integer(dump_only=True, allow_none=True)
    deleted_at = fields.DateTime(dump_only=True, allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)

    booth_tiers = fields.List(fields.Nested(MarketCatalogBoothTierSchema), dump_only=True)
