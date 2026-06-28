from __future__ import annotations

from marshmallow import Schema, fields, validate


class PosSessionSchema(Schema):
    session_number = fields.String(dump_only=True)
    opened_by_user_id = fields.Integer(required=True)
    closed_by_user_id = fields.Integer(dump_only=True)
    market_id = fields.Integer(allow_none=True)
    inventory_location_id = fields.Integer(allow_none=True)
    status = fields.String(dump_only=True)
    opening_cash = fields.Decimal(places=2, as_string=True)
    closing_cash = fields.Decimal(places=2, as_string=True, allow_none=True)
    expected_cash = fields.Decimal(places=2, as_string=True, dump_only=True)
    cash_difference = fields.Decimal(places=2, as_string=True, dump_only=True)
    opened_at = fields.DateTime(dump_only=True)
    closed_at = fields.DateTime(dump_only=True, allow_none=True)
    notes = fields.String(allow_none=True)


class PosCloseSessionSchema(Schema):
    closing_cash = fields.Decimal(places=2, required=True)
    notes = fields.String(allow_none=True)


class PosSaleItemSchema(Schema):
    pos_sale_id = fields.Integer(dump_only=True)
    product_id = fields.Integer(allow_none=True)
    quantity = fields.Integer(required=True, validate=validate.Range(min=1))
    unit_price = fields.Decimal(places=2, as_string=True)
    discount_amount = fields.Decimal(places=2, as_string=True, load_default=0)
    line_total = fields.Decimal(places=2, as_string=True)
    item_type = fields.String(
        validate=validate.OneOf(["product", "custom_item", "custom_deposit", "discount", "fee"]),
        load_default="product",
    )
    description = fields.String(required=True)
    custom_notes = fields.String(allow_none=True)


class PosSaleCreateSchema(Schema):
    payment_method = fields.String(
        required=True,
        validate=validate.OneOf(["cash", "card_external", "venmo", "cash_app", "apple_pay", "other"]),
    )
    amount_received = fields.Decimal(places=2, as_string=True, required=True)
    customer_id = fields.Integer(allow_none=True)
    notes = fields.String(allow_none=True)
    items = fields.List(fields.Nested(PosSaleItemSchema), required=True, validate=validate.Length(min=1))


class PosSaleSchema(Schema):
    pos_session_id = fields.Integer(dump_only=True)
    order_id = fields.Integer(dump_only=True, allow_none=True)
    customer_id = fields.Integer(allow_none=True)
    sale_number = fields.String(dump_only=True)
    subtotal = fields.Decimal(places=2, as_string=True)
    discount_total = fields.Decimal(places=2, as_string=True)
    tax_total = fields.Decimal(places=2, as_string=True)
    total = fields.Decimal(places=2, as_string=True)
    payment_method = fields.String()
    amount_received = fields.Decimal(places=2, as_string=True)
    change_due = fields.Decimal(places=2, as_string=True)
    status = fields.String(dump_only=True)
    notes = fields.String(allow_none=True)
    items = fields.List(fields.Nested(PosSaleItemSchema), dump_only=True)
