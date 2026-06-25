from __future__ import annotations

from decimal import Decimal

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileSize
from wtforms import (
    BooleanField,
    DecimalField,
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.forms.common import OptionalSelectField, enum_choices
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


class ProductStudioForm(FlaskForm):
    name = StringField("Product Name", validators=[DataRequired(), Length(max=160)])
    slug = StringField("Slug", validators=[DataRequired(), Length(max=180)])
    sku_base = StringField("Base SKU", validators=[Optional(), Length(max=80)])
    short_description = TextAreaField("Short Description", validators=[Optional()])
    description = TextAreaField("Full Description", validators=[Optional()])
    category_id = SelectField("Category", coerce=int, validators=[DataRequired()])
    collection_id = OptionalSelectField("Collection", coerce=int, validators=[Optional()])
    product_type = SelectField(
        "Product Type", choices=enum_choices(ProductType), validators=[DataRequired()]
    )
    status = SelectField("Status", choices=enum_choices(ProductStatus), validators=[DataRequired()])
    is_public = BooleanField("Publicly Visible", default=False)
    is_pos_visible = BooleanField("Visible In POS", default=True)
    is_featured = BooleanField("Featured", default=False)
    base_price = DecimalField("Base Price ($)", places=2, validators=[Optional(), NumberRange(min=0)])
    tags = TextAreaField("Tags", validators=[Optional()])
    care_instructions = TextAreaField("Care Instructions", validators=[Optional()])
    safety_notes = TextAreaField("Safety Notes", validators=[Optional()])
    submit = SubmitField("Save Product")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.category_id.choices = [
            (item.id, f"{item.name}") for item in Category.query.order_by(Category.name)
        ]
        self.collection_id.choices = [(0, "— No Collection —")] + [
            (item.id, f"{item.name}") for item in Collection.query.order_by(Collection.name)
        ]

    def validate_slug(self, field):
        existing = Product.query.filter_by(slug=field.data.strip()).first()
        if existing and getattr(self, "instance_id", None) != existing.id:
            from wtforms.validators import ValidationError
            raise ValidationError("A product with that slug already exists.")

    def validate_sku_base(self, field):
        if not field.data:
            return
        existing = Product.query.filter_by(sku_base=field.data.strip()).first()
        if existing and getattr(self, "instance_id", None) != existing.id:
            from wtforms.validators import ValidationError
            raise ValidationError("A product with that base SKU already exists.")

    def populate_product(self, product: Product) -> Product:
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
        product.base_price = self.base_price.data if self.base_price.data is not None else Decimal("0")
        product.tags = self.tags.data
        product.care_instructions = self.care_instructions.data
        product.safety_notes = self.safety_notes.data
        return product

    def load_from_product(self, product: Product) -> None:
        self.name.data = product.name
        self.slug.data = product.slug
        self.sku_base.data = product.sku_base
        self.short_description.data = product.short_description
        self.description.data = product.description
        self.category_id.data = product.category_id
        self.collection_id.data = product.collection_id or 0
        self.product_type.data = product.product_type.value
        self.status.data = product.status.value
        self.is_public.data = product.is_public
        self.is_pos_visible.data = product.is_pos_visible
        self.is_featured.data = product.is_featured
        self.base_price.data = product.base_price
        self.tags.data = product.tags
        self.care_instructions.data = product.care_instructions
        self.safety_notes.data = product.safety_notes


class VariantInlineForm(FlaskForm):
    sku = StringField("SKU", validators=[DataRequired(), Length(max=100)])
    name = StringField("Variant Name", validators=[DataRequired(), Length(max=160)])
    colorway = StringField("Colorway", validators=[Optional(), Length(max=120)])
    size = StringField("Size", validators=[Optional(), Length(max=120)])
    material_type = StringField("Material Type", validators=[Optional(), Length(max=120)])
    price = DecimalField("Price ($)", places=2, validators=[Optional(), NumberRange(min=0)])
    material_cost = DecimalField(
        "Material Cost ($)", places=2, validators=[Optional(), NumberRange(min=0)]
    )
    estimated_print_minutes = IntegerField(
        "Print Minutes", validators=[Optional(), NumberRange(min=0)], default=0
    )
    estimated_filament_grams = IntegerField(
        "Filament Grams", validators=[Optional(), NumberRange(min=0)], default=0
    )
    active = BooleanField("Active", default=True)
    pos_button_label = StringField("POS Button Label", validators=[Optional(), Length(max=120)])
    pos_sort_order = IntegerField(
        "POS Sort Order", validators=[Optional(), NumberRange(min=0)], default=0
    )


class ModelAssetUploadForm(FlaskForm):
    title = StringField("Model Title", validators=[DataRequired(), Length(max=160)])
    model_file = FileField(
        "3D Model File",
        validators=[
            DataRequired(),
            FileAllowed(
                ["stl", "glb", "gltf", "3mf", "obj"],
                "STL, GLB, GLTF, 3MF, and OBJ files are supported.",
            ),
            FileSize(max_size=256 * 1024 * 1024, message="File must be under 256 MB."),
        ],
    )
    source_type = SelectField(
        "Source Type", choices=enum_choices(ModelSourceType), validators=[DataRequired()]
    )
    source_url = StringField("Source URL", validators=[Optional(), Length(max=500)])
    designer_name = StringField("Designer Name", validators=[Optional(), Length(max=160)])
    license_type = StringField("License Type", validators=[Optional(), Length(max=160)])
    commercial_use_allowed = BooleanField("Commercial Use Allowed", default=False)
    notes = TextAreaField("Notes", validators=[Optional()])
    status = SelectField(
        "License Status", choices=enum_choices(LicenseStatus), validators=[DataRequired()]
    )

    def populate_asset(self, asset: ModelAsset) -> ModelAsset:
        asset.title = self.title.data.strip()
        asset.source_type = ModelSourceType(self.source_type.data)
        asset.source_url = self.source_url.data or None
        asset.designer_name = self.designer_name.data or None
        asset.license_type = self.license_type.data or None
        asset.commercial_use_allowed = bool(self.commercial_use_allowed.data)
        asset.notes = self.notes.data
        asset.status = LicenseStatus(self.status.data)
        asset.analysis_status = "pending"
        return asset
