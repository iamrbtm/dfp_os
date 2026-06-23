from marshmallow import Schema, fields


class BusinessSchema(Schema):
    id = fields.Int(dump_only=True)
    name = fields.Str(required=True)
    slug = fields.Str(required=True)
    legal_name = fields.Str(allow_none=True)
    public_name = fields.Str(allow_none=True)
    contact_email = fields.Str(allow_none=True)
    phone = fields.Str(allow_none=True)
    website_url = fields.Str(allow_none=True)
    address_line1 = fields.Str(allow_none=True)
    address_line2 = fields.Str(allow_none=True)
    city = fields.Str(allow_none=True)
    state = fields.Str(allow_none=True)
    postal_code = fields.Str(allow_none=True)
    timezone = fields.Str(required=True)
    currency = fields.Str(required=True)
    is_active = fields.Bool(load_default=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class FeatureFlagSchema(Schema):
    id = fields.Int(dump_only=True)
    key = fields.Str(required=True)
    enabled = fields.Bool(load_default=True)
    description = fields.Str(allow_none=True)
    business_id = fields.Int(allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class PrepTaskTemplateSchema(Schema):
    id = fields.Int(dump_only=True)
    title = fields.Str(required=True)
    category = fields.Str(required=True)
    description = fields.Str(allow_none=True)
    default_due_days_before = fields.Int(required=True)
    default_enabled = fields.Bool(load_default=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class PrepTaskSchema(Schema):
    id = fields.Int(dump_only=True)
    market_id = fields.Int(allow_none=True)
    template_id = fields.Int(allow_none=True)
    title = fields.Str(required=True)
    category = fields.Str(required=True)
    status = fields.Str(required=True)
    assigned_user_id = fields.Int(allow_none=True)
    due_at = fields.DateTime(allow_none=True)
    completed_at = fields.DateTime(allow_none=True, dump_only=True)
    source = fields.Str(required=True)
    notes = fields.Str(allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
