from __future__ import annotations

from marshmallow import Schema, fields


class CustomerSchema(Schema):
    id = fields.Integer(dump_only=True)
    first_name = fields.String(required=True)
    last_name = fields.String(required=True)
    email = fields.String(allow_none=True)
    phone = fields.String(allow_none=True)
    address_line_1 = fields.String(allow_none=True)
    address_line_2 = fields.String(allow_none=True)
    city = fields.String(allow_none=True)
    state = fields.String(allow_none=True)
    zip_code = fields.String(allow_none=True)
    notes = fields.String(allow_none=True)
    is_active = fields.Boolean()
    deleted_at = fields.DateTime(dump_only=True, allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
