from __future__ import annotations

from marshmallow import Schema, fields


class PrintJobSchema(Schema):
    id = fields.Integer(dump_only=True)
    order_item_id = fields.Integer(allow_none=True)
    product_id = fields.Integer(allow_none=True)
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


class PrintFailureAutopsySchema(Schema):
    id = fields.Integer(dump_only=True)
    print_job_id = fields.Integer(required=True)
    printer_id = fields.Integer(allow_none=True)
    product_id = fields.Integer(allow_none=True)
    filament_spool_id = fields.Integer(allow_none=True)
    user_id = fields.Integer(allow_none=True)
    model_asset_id = fields.Integer(allow_none=True)
    category = fields.String(required=True)
    severity = fields.String(required=True)
    notes = fields.String(allow_none=True)
    photo_reference = fields.String(allow_none=True)
    corrective_action = fields.String(allow_none=True)
    maintenance_required = fields.Boolean()
    resolved = fields.Boolean()
    resolution_notes = fields.String(allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
