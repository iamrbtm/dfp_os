from __future__ import annotations

from marshmallow import Schema, fields


class PrintJobSchema(Schema):
    id = fields.Integer(dump_only=True)
    order_item_id = fields.Integer(allow_none=True)
    product_id = fields.Integer(allow_none=True)
    variant_id = fields.Integer(allow_none=True)
    printer_id = fields.Integer(allow_none=True)
    assigned_to_id = fields.Integer(allow_none=True)
    status = fields.String(required=True)
    priority = fields.Integer()
    started_at = fields.DateTime(allow_none=True)
    completed_at = fields.DateTime(allow_none=True)
    estimated_minutes = fields.Integer()
    actual_minutes = fields.Integer(allow_none=True)
    filament_used_grams = fields.Integer(allow_none=True)
    failure_reason = fields.String(allow_none=True)
    notes = fields.String(allow_none=True)
    label = fields.String(allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
