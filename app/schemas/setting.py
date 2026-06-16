from marshmallow import Schema, fields


class SettingSchema(Schema):
    id = fields.Int(dump_only=True)
    key = fields.Str(required=True)
    value = fields.Str(required=True)
    description = fields.Str(allow_none=True)
    type = fields.Str(load_default="string")
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
