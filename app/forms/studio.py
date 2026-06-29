from __future__ import annotations

from decimal import Decimal

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileSize
from wtforms import (
    BooleanField,
    DateTimeLocalField,
    DecimalField,
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
    ModelSourceType,
    Product,
    ProductStatus,
    ProductType,
)
from app.models.catalog import LicenseStatus
from app.utils import slugify


class ProductStudioForm(FlaskForm):
    name = StringField("Product Name", validators=[DataRequired(), Length(max=160)])
    slug = StringField("Slug", validators=[Optional(), Length(max=180)])
    sku_base = StringField("SKU", validators=[Optional(), Length(max=80)])
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
    base_price = DecimalField(
        "Base Price ($)", places=2, validators=[Optional(), NumberRange(min=0)]
    )
    tags = TextAreaField("Tags", validators=[Optional()])
    care_instructions = TextAreaField("Care Instructions", validators=[Optional()])
    safety_notes = TextAreaField("Safety Notes", validators=[Optional()])
    license_status = SelectField(
        "License Status", choices=enum_choices(LicenseStatus), validators=[DataRequired()]
    )
    design_source = StringField("Design Source", validators=[Optional(), Length(max=255)])
    commercial_license_notes = TextAreaField("Commercial License Notes", validators=[Optional()])
    model_source_type = SelectField(
        "Model Source Type",
        choices=enum_choices(ModelSourceType),
        validators=[DataRequired()],
    )
    model_source_url = StringField("Model Source URL", validators=[Optional(), Length(max=500)])
    model_designer_name = StringField("Model Designer", validators=[Optional(), Length(max=160)])
    model_license_type = StringField("Model License Type", validators=[Optional(), Length(max=160)])
    model_commercial_use_allowed = BooleanField("Model Commercial Use Allowed", default=False)
    model_license_expiration = DateTimeLocalField(
        "Model License Expiration",
        format="%Y-%m-%dT%H:%M",
        validators=[Optional()],
    )
    model_notes = TextAreaField("Model Notes", validators=[Optional()])
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
        raw = (field.data or "").strip()
        if not raw:
            raw = slugify((self.name.data or "").strip())
            field.data = raw
        if not raw:
            return
        existing = Product.query.filter_by(slug=raw).first()
        if existing and getattr(self, "instance_id", None) != existing.id:
            from wtforms.validators import ValidationError

            raise ValidationError("A product with that slug already exists.")

    def validate_sku_base(self, field):
        if not field.data:
            return
        existing = Product.query.filter_by(sku_base=field.data.strip()).first()
        if existing and getattr(self, "instance_id", None) != existing.id:
            from wtforms.validators import ValidationError

            raise ValidationError("A product with that SKU already exists.")

    def populate_product(self, product: Product) -> Product:
        product.name = self.name.data.strip()
        product.slug = slugify(self.slug.data or "") or slugify(self.name.data.strip())
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
        product.license_status = LicenseStatus(self.license_status.data)
        product.design_source = self.design_source.data or None
        product.commercial_license_notes = self.commercial_license_notes.data
        product.model_source_type = ModelSourceType(self.model_source_type.data)
        product.model_source_url = self.model_source_url.data or None
        product.model_designer_name = self.model_designer_name.data or None
        product.model_license_type = self.model_license_type.data or None
        product.model_commercial_use_allowed = bool(self.model_commercial_use_allowed.data)
        product.model_license_expiration = self.model_license_expiration.data
        product.model_notes = self.model_notes.data
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
        self.license_status.data = product.license_status.value
        self.design_source.data = product.design_source
        self.commercial_license_notes.data = product.commercial_license_notes
        self.model_source_type.data = product.model_source_type.value
        self.model_source_url.data = product.model_source_url
        self.model_designer_name.data = product.model_designer_name
        self.model_license_type.data = product.model_license_type
        self.model_commercial_use_allowed.data = product.model_commercial_use_allowed
        self.model_license_expiration.data = product.model_license_expiration
        self.model_notes.data = product.model_notes


class ProductModelUploadForm(FlaskForm):
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
