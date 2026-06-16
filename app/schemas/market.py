from __future__ import annotations

from marshmallow import Schema, fields


class MarketSchema(Schema):
    id = fields.Integer(dump_only=True)
    name = fields.String(required=True)
    location_name = fields.String(allow_none=True)
    address = fields.String(allow_none=True)
    city = fields.String(allow_none=True)
    state = fields.String(allow_none=True)
    event_date = fields.Date(allow_none=True)
    start_time = fields.String(allow_none=True)
    end_time = fields.String(allow_none=True)
    booth_fee = fields.Decimal(as_string=True, allow_none=True)
    application_fee = fields.Decimal(as_string=True, allow_none=True)
    status = fields.String(required=True)
    expected_traffic = fields.String(allow_none=True)
    actual_revenue = fields.Decimal(as_string=True, allow_none=True)
    actual_profit = fields.Decimal(as_string=True, allow_none=True)
    notes = fields.String(allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class MarketPackingListSchema(Schema):
    id = fields.Integer(dump_only=True)
    market_id = fields.Integer(required=True)
    product_id = fields.Integer(required=True)
    variant_id = fields.Integer(allow_none=True)
    planned_quantity = fields.Integer(allow_none=True)
    packed_quantity = fields.Integer(allow_none=True)
    sold_quantity = fields.Integer(allow_none=True)
    returned_quantity = fields.Integer(allow_none=True)
    notes = fields.String(allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
