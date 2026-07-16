from __future__ import annotations

from marshmallow import Schema, fields


class PickupLocationSchema(Schema):
    id = fields.Integer(dump_only=True)
    name = fields.String(required=True)
    location_type = fields.String(required=True)
    address = fields.String(allow_none=True)
    instructions = fields.String(allow_none=True)
    active = fields.Boolean()
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class PickupSlotSchema(Schema):
    id = fields.Integer(dump_only=True)
    location_id = fields.Integer(required=True)
    market_id = fields.Integer(allow_none=True)
    starts_at = fields.DateTime(required=True)
    ends_at = fields.DateTime(required=True)
    capacity = fields.Integer()
    status = fields.String()
    public_label = fields.String(allow_none=True)
    instructions = fields.String(allow_none=True)
    available_capacity = fields.Integer(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
