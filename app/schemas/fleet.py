from __future__ import annotations

from marshmallow import Schema, fields


class PrinterSchema(Schema):
    id = fields.Integer(dump_only=True)
    name = fields.String(required=True)
    model = fields.String(required=True)
    serial_number = fields.String(allow_none=True)
    status = fields.String(required=True)
    location = fields.String(allow_none=True)
    has_ams = fields.Boolean()
    default_nozzle_size = fields.String(allow_none=True)
    notes = fields.String(allow_none=True)
    purchase_date = fields.DateTime(allow_none=True)
    maintenance_notes = fields.String(allow_none=True)
    total_print_hours = fields.Integer()
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class AMSUnitSchema(Schema):
    id = fields.Integer(dump_only=True)
    name = fields.String(required=True)
    type = fields.String(required=True)
    status = fields.String(required=True)
    assigned_printer_id = fields.Integer(allow_none=True)
    slot_count = fields.Integer()
    notes = fields.String(allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
