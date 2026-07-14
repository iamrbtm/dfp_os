from __future__ import annotations

from marshmallow import Schema, fields


class CustomRequestSchema(Schema):
    id = fields.Integer(dump_only=True)
    name = fields.String(required=True)
    email = fields.String(required=True)
    phone = fields.String(allow_none=True)
    description = fields.String(required=True)
    reference_image_paths = fields.String(allow_none=True)
    estimated_budget = fields.Decimal(as_string=True, allow_none=True)
    deadline = fields.DateTime(allow_none=True)
    status = fields.String(required=True)
    subtotal = fields.Decimal(as_string=True, allow_none=True)
    tax = fields.Decimal(as_string=True, allow_none=True)
    discount = fields.Decimal(as_string=True, allow_none=True)
    total = fields.Decimal(as_string=True, allow_none=True)
    amount_paid = fields.Decimal(as_string=True, allow_none=True)
    admin_notes = fields.String(allow_none=True)
    internal_notes = fields.String(allow_none=True)
    converted_to_order_id = fields.Integer(allow_none=True)
    pickup_slot_id = fields.Integer(allow_none=True)
    pickup_status = fields.String(allow_none=True)
    pickup_ready_at = fields.DateTime(allow_none=True)
    picked_up_at = fields.DateTime(allow_none=True)
    pickup_no_show_at = fields.DateTime(allow_none=True)
    pickup_notes = fields.String(allow_none=True)
    customer_id = fields.Integer(allow_none=True)
    source = fields.String(allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
