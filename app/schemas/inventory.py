from __future__ import annotations

from decimal import Decimal

from marshmallow import Schema, fields


class FilamentSpoolSchema(Schema):
    id = fields.Integer(dump_only=True)
    brand = fields.String(required=True)
    material_type = fields.String(required=True)
    color_name = fields.String(required=True)
    color_hex = fields.String(allow_none=True)
    spool_weight_grams = fields.Integer(load_default=0)
    remaining_weight_grams = fields.Integer(load_default=0)
    cost_per_spool = fields.Decimal(as_string=True, load_default=Decimal("0.00"))
    cost_per_gram = fields.Decimal(as_string=True, load_default=Decimal("0.00"))
    supplier = fields.String(allow_none=True)
    purchase_date = fields.DateTime(allow_none=True)
    storage_location = fields.String(allow_none=True)
    status = fields.String(required=True)
    reorder_threshold_grams = fields.Integer(load_default=0)
    notes = fields.String(allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class InventoryLocationSchema(Schema):
    id = fields.Integer(dump_only=True)
    name = fields.String(required=True)
    type = fields.String(required=True)
    description = fields.String(allow_none=True)
    active = fields.Boolean()
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class InventoryRecordSchema(Schema):
    id = fields.Integer(dump_only=True)
    product_id = fields.Integer(required=True)
    location_id = fields.Integer(required=True)
    quantity_on_hand = fields.Integer(load_default=0)
    quantity_reserved = fields.Integer(load_default=0)
    reorder_threshold = fields.Integer(load_default=0)
    reorder_target = fields.Integer(load_default=0)
    last_counted_at = fields.DateTime(allow_none=True)
    quantity_available = fields.Integer(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
