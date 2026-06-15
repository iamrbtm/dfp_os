from __future__ import annotations

from decimal import Decimal

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DecimalField,
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.fields.datetime import DateTimeLocalField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, URL, ValidationError

from app.forms.common import OptionalSelectField, decimal_or_zero, enum_choices
from app.models import (
    Category,
    Collection,
    LicenseStatus,
    ModelAsset,
    ModelSourceType,
    Product,
    ProductStatus,
    ProductType,
    ProductVariant,
)


class CategoryForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=120)])
    slug = StringField("Slug", validators=[DataRequired(), Length(max=160)])
    description = TextAreaField("Description", validators=[Optional()])
    sort_order = IntegerField("Sort Order", validators=[Optional(), NumberRange(min=0)], default=0)
    is_public = BooleanField("Publicly Visible", default=True)
    is_pos_visible = BooleanField("Visible In POS", default=True)
    submit = SubmitField("Save category")

    def validate_slug(self, field):
        existing = Category.query.filter_by(slug=field.data.strip()).first()
        if existing and getattr(self, "instance_id", None) != existing.id:
            raise ValidationError("A category with that slug already exists.")

    def apply(self, category: Category) -> Category:
        category.name = self.name.data.strip()
        category.slug = self.slug.data.strip()
        category.description = self.description.data
        category.sort_order = self.sort_order.data or 0
        category.is_public = bool(self.is_public.data)
        category.is_pos_visible = bool(self.is_pos_visible.data)
        return category


class CollectionForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=120)])
    slug = StringField("Slug", validators=[DataRequired(), Length(max=160)])
    description = TextAreaField("Description", validators=[Optional()])
    sort_order = IntegerField("Sort Order", validators=[Optional(), NumberRange(min=0)], default=0)
    is_public = BooleanField("Publicly Visible", default=True)
    submit = SubmitField("Save collection")

    def validate_slug(self, field):
        existing = Collection.query.filter_by(slug=field.data.strip()).first()
        if existing and getattr(self, "instance_id", None) != existing.id:
            raise ValidationError("A collection with that slug already exists.")

    def apply(self, collection: Collection) -> Collection:
        collection.name = self.name.data.strip()
        collection.slug = self.slug.data.strip()
        collection.description = self.description.data
        collection.sort_order = self.sort_order.data or 0
        collection.is_public = bool(self.is_public.data)
        return collection


class ProductForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=160)])
    slug = StringField("Slug", validators=[DataRequired(), Length(max=180)])
    sku_base = StringField("Base SKU", validators=[Optional(), Length(max=80)])
    short_description = TextAreaField("Short Description", validators=[Optional()])
    description = TextAreaField("Description", validators=[Optional()])
    category_id = SelectField("Category", coerce=int, validators=[DataRequired()])
    collection_id = OptionalSelectField("Collection", coerce=int, validators=[Optional()])
    product_type = SelectField(
        "Product Type", choices=enum_choices(ProductType), validators=[DataRequired()]
    )
    status = SelectField("Status", choices=enum_choices(ProductStatus), validators=[DataRequired()])
    is_public = BooleanField("Publicly Visible", default=False)
    is_pos_visible = BooleanField("Visible In POS", default=True)
    is_featured = BooleanField("Featured", default=False)
    base_price = DecimalField("Base Price", places=2, validators=[Optional(), NumberRange(min=0)])
    estimated_material_cost = DecimalField(
        "Estimated Material Cost", places=2, validators=[Optional(), NumberRange(min=0)]
    )
    estimated_labor_minutes = IntegerField(
        "Estimated Labor Minutes", validators=[Optional(), NumberRange(min=0)], default=0
    )
    estimated_print_minutes = IntegerField(
        "Estimated Print Minutes", validators=[Optional(), NumberRange(min=0)], default=0
    )
    estimated_profit = DecimalField(
        "Estimated Profit", places=2, validators=[Optional()], default=Decimal("0")
    )
    default_image_path = StringField("Default Image Path", validators=[Optional(), Length(max=255)])
    tags = TextAreaField("Tags", validators=[Optional()])
    care_instructions = TextAreaField("Care Instructions", validators=[Optional()])
    safety_notes = TextAreaField("Safety Notes", validators=[Optional()])
    license_status = SelectField(
        "License Status", choices=enum_choices(LicenseStatus), validators=[DataRequired()]
    )
    design_source = StringField("Design Source", validators=[Optional(), Length(max=255)])
    commercial_license_notes = TextAreaField("Commercial License Notes", validators=[Optional()])
    submit = SubmitField("Save product")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.category_id.choices = [
            (item.id, item.name) for item in Category.query.order_by(Category.name)
        ]
        self.collection_id.choices = [(0, "No collection")] + [
            (item.id, item.name) for item in Collection.query.order_by(Collection.name)
        ]

    def validate_slug(self, field):
        existing = Product.query.filter_by(slug=field.data.strip()).first()
        if existing and getattr(self, "instance_id", None) != existing.id:
            raise ValidationError("A product with that slug already exists.")

    def validate_sku_base(self, field):
        if not field.data:
            return
        existing = Product.query.filter_by(sku_base=field.data.strip()).first()
        if existing and getattr(self, "instance_id", None) != existing.id:
            raise ValidationError("A product with that base SKU already exists.")

    def apply(self, product: Product) -> Product:
        product.name = self.name.data.strip()
        product.slug = self.slug.data.strip()
        product.sku_base = self.sku_base.data.strip() if self.sku_base.data else None
        product.short_description = self.short_description.data
        product.description = self.description.data
        product.category_id = self.category_id.data
        product.collection_id = self.collection_id.data or None
        product.product_type = ProductType(self.product_type.data)
        product.status = ProductStatus(self.status.data)
        product.is_public = bool(self.is_public.data)
        product.is_pos_visible = bool(self.is_pos_visible.data)
        product.is_featured = bool(self.is_featured.data)
        product.base_price = decimal_or_zero(self.base_price.data)
        product.estimated_material_cost = decimal_or_zero(self.estimated_material_cost.data)
        product.estimated_labor_minutes = self.estimated_labor_minutes.data or 0
        product.estimated_print_minutes = self.estimated_print_minutes.data or 0
        product.estimated_profit = decimal_or_zero(self.estimated_profit.data)
        product.default_image_path = self.default_image_path.data or None
        product.tags = self.tags.data
        product.care_instructions = self.care_instructions.data
        product.safety_notes = self.safety_notes.data
        product.license_status = LicenseStatus(self.license_status.data)
        product.design_source = self.design_source.data or None
        product.commercial_license_notes = self.commercial_license_notes.data
        return product


class ProductVariantForm(FlaskForm):
    product_id = SelectField("Product", coerce=int, validators=[DataRequired()])
    sku = StringField("SKU", validators=[DataRequired(), Length(max=100)])
    name = StringField("Variant Name", validators=[DataRequired(), Length(max=160)])
    colorway = StringField("Colorway", validators=[Optional(), Length(max=120)])
    size = StringField("Size", validators=[Optional(), Length(max=120)])
    material_type = StringField("Material Type", validators=[Optional(), Length(max=120)])
    price = DecimalField("Price", places=2, validators=[Optional(), NumberRange(min=0)])
    material_cost = DecimalField(
        "Material Cost", places=2, validators=[Optional(), NumberRange(min=0)]
    )
    estimated_print_minutes = IntegerField(
        "Estimated Print Minutes", validators=[Optional(), NumberRange(min=0)], default=0
    )
    estimated_filament_grams = IntegerField(
        "Estimated Filament Grams", validators=[Optional(), NumberRange(min=0)], default=0
    )
    active = BooleanField("Active", default=True)
    pos_button_label = StringField("POS Button Label", validators=[Optional(), Length(max=120)])
    pos_sort_order = IntegerField(
        "POS Sort Order", validators=[Optional(), NumberRange(min=0)], default=0
    )
    barcode_or_qr_code = StringField("Barcode or QR Code", validators=[Optional(), Length(max=255)])
    submit = SubmitField("Save variant")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.product_id.choices = [
            (item.id, item.name) for item in Product.query.order_by(Product.name)
        ]

    def validate_sku(self, field):
        existing = ProductVariant.query.filter_by(sku=field.data.strip()).first()
        if existing and getattr(self, "instance_id", None) != existing.id:
            raise ValidationError("A variant with that SKU already exists.")

    def apply(self, variant: ProductVariant) -> ProductVariant:
        variant.product_id = self.product_id.data
        variant.sku = self.sku.data.strip()
        variant.name = self.name.data.strip()
        variant.colorway = self.colorway.data or None
        variant.size = self.size.data or None
        variant.material_type = self.material_type.data or None
        variant.price = decimal_or_zero(self.price.data)
        variant.material_cost = decimal_or_zero(self.material_cost.data)
        variant.estimated_print_minutes = self.estimated_print_minutes.data or 0
        variant.estimated_filament_grams = self.estimated_filament_grams.data or 0
        variant.active = bool(self.active.data)
        variant.pos_button_label = self.pos_button_label.data or None
        variant.pos_sort_order = self.pos_sort_order.data or 0
        variant.barcode_or_qr_code = self.barcode_or_qr_code.data or None
        return variant


class ModelAssetForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=160)])
    source_type = SelectField(
        "Source Type", choices=enum_choices(ModelSourceType), validators=[DataRequired()]
    )
    source_url = StringField("Source URL", validators=[Optional(), URL(), Length(max=500)])
    designer_name = StringField("Designer Name", validators=[Optional(), Length(max=160)])
    license_type = StringField("License Type", validators=[Optional(), Length(max=160)])
    commercial_use_allowed = BooleanField("Commercial Use Allowed", default=False)
    license_expiration = DateTimeLocalField(
        "License Expiration",
        format="%Y-%m-%dT%H:%M",
        validators=[Optional()],
    )
    proof_of_license_path = StringField(
        "Proof Of License Path", validators=[Optional(), Length(max=255)]
    )
    file_location = StringField("File Location", validators=[Optional(), Length(max=255)])
    related_product_id = OptionalSelectField("Related Product", coerce=int, validators=[Optional()])
    notes = TextAreaField("Notes", validators=[Optional()])
    status = SelectField("Status", choices=enum_choices(LicenseStatus), validators=[DataRequired()])
    submit = SubmitField("Save model asset")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.related_product_id.choices = [(0, "No linked product")] + [
            (item.id, item.name) for item in Product.query.order_by(Product.name)
        ]

    def apply(self, asset: ModelAsset) -> ModelAsset:
        asset.title = self.title.data.strip()
        asset.source_type = ModelSourceType(self.source_type.data)
        asset.source_url = self.source_url.data or None
        asset.designer_name = self.designer_name.data or None
        asset.license_type = self.license_type.data or None
        asset.commercial_use_allowed = bool(self.commercial_use_allowed.data)
        asset.license_expiration = self.license_expiration.data
        asset.proof_of_license_path = self.proof_of_license_path.data or None
        asset.file_location = self.file_location.data or None
        asset.related_product_id = self.related_product_id.data or None
        asset.notes = self.notes.data
        asset.status = LicenseStatus(self.status.data)
        return asset
