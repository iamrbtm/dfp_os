from __future__ import annotations

from marshmallow import Schema, fields


class ExpenseSchema(Schema):
    id = fields.Integer(dump_only=True)
    date = fields.Date(required=True)
    vendor = fields.String(required=True)
    category = fields.String(required=True)
    description = fields.String(allow_none=True)
    amount = fields.Decimal(as_string=True, required=True)
    payment_method = fields.String(allow_none=True)
    related_market_id = fields.Integer(allow_none=True)
    related_order_id = fields.Integer(allow_none=True)
    receipt_file_path = fields.String(allow_none=True)
    tax_deductible = fields.Boolean()
    notes = fields.String(allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
