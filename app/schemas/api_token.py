from marshmallow import Schema, fields


class ApiTokenSchema(Schema):
    id = fields.Int(dump_only=True)
    name = fields.Str(required=True)
    prefix = fields.Str(dump_only=True)
    scopes = fields.Str(load_default="")
    is_active = fields.Bool(dump_only=True)
    last_used_at = fields.DateTime(dump_only=True, allow_none=True)
    expires_at = fields.DateTime(allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    raw_token = fields.Str(dump_only=True)
