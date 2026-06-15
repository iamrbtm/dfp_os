from __future__ import annotations

from marshmallow import Schema, fields


class OrderItemSchema(Schema):
    id = fields.Integer(dump_only=True)
    order_id = fields.Integer(dump_only=True)
    product_id = fields.Integer(allow_none=True)
    variant_id = fields.Integer(allow_none=True)
    quantity = fields.Integer()
    unit_price = fields.Decimal(as_string=True)
    line_total = fields.Decimal(as_string=True)
    is_custom_item = fields.Boolean()
    custom_description = fields.String(allow_none=True)
    notes = fields.String(allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class PaymentSchema(Schema):
    id = fields.Integer(dump_only=True)
    order_id = fields.Integer(dump_only=True)
    amount = fields.Decimal(as_string=True)
    method = fields.String(required=True)
    reference = fields.String(allow_none=True)
    notes = fields.String(allow_none=True)
    payment_date = fields.DateTime(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class OrderSchema(Schema):
    id = fields.Integer(dump_only=True)
    order_number = fields.String(dump_only=True)
    customer_id = fields.Integer(allow_none=True)
    status = fields.String(required=True)
    source = fields.String(required=True)
    market_id = fields.Integer(allow_none=True)
    pos_session_id = fields.Integer(allow_none=True)
    notes = fields.String(allow_none=True)
    internal_notes = fields.String(allow_none=True)
    subtotal = fields.Decimal(as_string=True)
    tax_total = fields.Decimal(as_string=True)
    discount_total = fields.Decimal(as_string=True)
    total = fields.Decimal(as_string=True)
    paid_amount = fields.Decimal(as_string=True)
    deleted_at = fields.DateTime(dump_only=True, allow_none=True)
    completed_at = fields.DateTime(allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    items = fields.List(fields.Nested(OrderItemSchema), dump_only=True)
    payments = fields.List(fields.Nested(PaymentSchema), dump_only=True)
