from __future__ import annotations

from marshmallow import Schema, fields


class PaginationSchema(Schema):
    page = fields.Integer(required=True)
    per_page = fields.Integer(required=True)
    total = fields.Integer(required=True)
    pages = fields.Integer(required=True)


class CategorySchema(Schema):
    id = fields.Integer(dump_only=True)
    name = fields.String(required=True)
    slug = fields.String(required=True)
    description = fields.String(allow_none=True)
    sort_order = fields.Integer()
    is_public = fields.Boolean()
    is_pos_visible = fields.Boolean()
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class CollectionSchema(Schema):
    id = fields.Integer(dump_only=True)
    name = fields.String(required=True)
    slug = fields.String(required=True)
    description = fields.String(allow_none=True)
    is_public = fields.Boolean()
    sort_order = fields.Integer()
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class ProductSchema(Schema):
    id = fields.Integer(dump_only=True)
    name = fields.String(required=True)
    slug = fields.String(required=True)
    sku_base = fields.String(allow_none=True)
    short_description = fields.String(allow_none=True)
    description = fields.String(allow_none=True)
    category_id = fields.Integer(required=True)
    collection_id = fields.Integer(allow_none=True)
    product_type = fields.String(required=True)
    status = fields.String(required=True)
    is_public = fields.Boolean()
    is_pos_visible = fields.Boolean()
    is_featured = fields.Boolean()
    base_price = fields.Decimal(as_string=True)
    estimated_material_cost = fields.Decimal(as_string=True)
    estimated_labor_minutes = fields.Integer()
    estimated_print_minutes = fields.Integer()
    estimated_profit = fields.Decimal(as_string=True)
    default_image_path = fields.String(allow_none=True)
    tags = fields.String(allow_none=True)
    care_instructions = fields.String(allow_none=True)
    safety_notes = fields.String(allow_none=True)
    license_status = fields.String(required=True)
    design_source = fields.String(allow_none=True)
    commercial_license_notes = fields.String(allow_none=True)
    model_source_type = fields.String()
    model_source_url = fields.String(allow_none=True)
    model_designer_name = fields.String(allow_none=True)
    model_license_type = fields.String(allow_none=True)
    model_commercial_use_allowed = fields.Boolean()
    model_license_expiration = fields.DateTime(allow_none=True)
    model_file_path = fields.String(allow_none=True)
    model_notes = fields.String(allow_none=True)
    analysis_status = fields.String(allow_none=True)
    analysis_error = fields.String(allow_none=True)
    analysis_requested_at = fields.DateTime(dump_only=True, allow_none=True)
    analysis_completed_at = fields.DateTime(dump_only=True, allow_none=True)
    parsed_volume_mm3 = fields.Decimal(as_string=True, allow_none=True)
    parsed_surface_area_mm2 = fields.Decimal(as_string=True, allow_none=True)
    parsed_triangle_count = fields.Integer(allow_none=True)
    parsed_filament_grams = fields.Decimal(as_string=True, allow_none=True)
    parsed_print_minutes = fields.Decimal(as_string=True, allow_none=True)
    parsed_material_cost = fields.Decimal(as_string=True, allow_none=True)
    convert_status = fields.String(allow_none=True)
    conversion_error = fields.String(allow_none=True)
    converted_model_path = fields.String(allow_none=True)
    gcode_path = fields.String(allow_none=True)
    deleted_at = fields.DateTime(dump_only=True, allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class ResourceListEnvelope(Schema):
    data = fields.List(fields.Dict(), required=True)
    pagination = fields.Nested(PaginationSchema, required=True)
