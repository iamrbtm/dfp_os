from __future__ import annotations

from marshmallow import Schema, fields


class FilamentSpoolSchema(Schema):
    id = fields.Integer(dump_only=True)
    brand = fields.String(required=True)
    material_type = fields.String(required=True)
    color_name = fields.String(required=True)
    color_hex = fields.String(allow_none=True)
    spool_weight_grams = fields.Integer()
    remaining_weight_grams = fields.Integer()
    cost_per_spool = fields.Decimal(as_string=True)
    cost_per_gram = fields.Decimal(as_string=True)
    supplier = fields.String(allow_none=True)
    purchase_date = fields.DateTime(allow_none=True)
    storage_location = fields.String(allow_none=True)
    status = fields.String(required=True)
    reorder_threshold_grams = fields.Integer()
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
    variant_id = fields.Integer(allow_none=True)
    location_id = fields.Integer(required=True)
    quantity_on_hand = fields.Integer()
    quantity_reserved = fields.Integer()
    reorder_threshold = fields.Integer()
    reorder_target = fields.Integer()
    last_counted_at = fields.DateTime(allow_none=True)
    quantity_available = fields.Integer(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
