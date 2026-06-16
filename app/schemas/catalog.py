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
    deleted_at = fields.DateTime(dump_only=True, allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class ProductVariantSchema(Schema):
    id = fields.Integer(dump_only=True)
    product_id = fields.Integer(required=True)
    sku = fields.String(required=True)
    name = fields.String(required=True)
    colorway = fields.String(allow_none=True)
    size = fields.String(allow_none=True)
    material_type = fields.String(allow_none=True)
    price = fields.Decimal(as_string=True)
    material_cost = fields.Decimal(as_string=True)
    estimated_print_minutes = fields.Integer()
    estimated_filament_grams = fields.Integer()
    active = fields.Boolean()
    pos_button_label = fields.String(allow_none=True)
    pos_sort_order = fields.Integer()
    barcode_or_qr_code = fields.String(allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class ModelAssetSchema(Schema):
    id = fields.Integer(dump_only=True)
    title = fields.String(required=True)
    source_type = fields.String(required=True)
    source_url = fields.String(allow_none=True)
    designer_name = fields.String(allow_none=True)
    license_type = fields.String(allow_none=True)
    commercial_use_allowed = fields.Boolean()
    license_expiration = fields.DateTime(allow_none=True)
    proof_of_license_path = fields.String(allow_none=True)
    file_location = fields.String(allow_none=True)
    related_product_id = fields.Integer(allow_none=True)
    notes = fields.String(allow_none=True)
    status = fields.String(required=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class ResourceListEnvelope(Schema):
    data = fields.List(fields.Dict(), required=True)
    pagination = fields.Nested(PaginationSchema, required=True)
