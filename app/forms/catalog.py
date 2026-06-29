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
    Product,
    ProductStatus,
    ProductType,
)
from app.utils import slugify


class CategoryForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=120)])
    slug = StringField("Slug", validators=[Optional(), Length(max=160)])
    description = TextAreaField("Description", validators=[Optional()])
    sort_order = IntegerField("Sort Order", validators=[Optional(), NumberRange(min=0)], default=0)
    is_public = BooleanField("Publicly Visible", default=True)
    is_pos_visible = BooleanField("Visible In POS", default=True)
    submit = SubmitField("Save category")

    def validate_slug(self, field):
        raw = (field.data or "").strip()
        if not raw:
            raw = slugify((self.name.data or "").strip())
            field.data = raw
        if not raw:
            return
        existing = Category.query.filter_by(slug=raw).first()
        if existing and getattr(self, "instance_id", None) != existing.id:
            raise ValidationError("A category with that slug already exists.")

    def apply(self, category: Category) -> Category:
        category.name = self.name.data.strip()
        category.slug = slugify(self.slug.data or "") or slugify(self.name.data.strip())
        category.description = self.description.data
        category.sort_order = self.sort_order.data or 0
        category.is_public = bool(self.is_public.data)
        category.is_pos_visible = bool(self.is_pos_visible.data)
        return category


class CollectionForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=120)])
    slug = StringField("Slug", validators=[Optional(), Length(max=160)])
    description = TextAreaField("Description", validators=[Optional()])
    sort_order = IntegerField("Sort Order", validators=[Optional(), NumberRange(min=0)], default=0)
    is_public = BooleanField("Publicly Visible", default=True)
    submit = SubmitField("Save collection")

    def validate_slug(self, field):
        raw = (field.data or "").strip()
        if not raw:
            raw = slugify((self.name.data or "").strip())
            field.data = raw
        if not raw:
            return
        existing = Collection.query.filter_by(slug=raw).first()
        if existing and getattr(self, "instance_id", None) != existing.id:
            raise ValidationError("A collection with that slug already exists.")

    def apply(self, collection: Collection) -> Collection:
        collection.name = self.name.data.strip()
        collection.slug = slugify(self.slug.data or "") or slugify(self.name.data.strip())
        collection.description = self.description.data
        collection.sort_order = self.sort_order.data or 0
        collection.is_public = bool(self.is_public.data)
        return collection


class ProductForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=160)])
    slug = StringField("Slug", validators=[Optional(), Length(max=180)])
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
        raw = (field.data or "").strip()
        if not raw:
            raw = slugify((self.name.data or "").strip())
            field.data = raw
        if not raw:
            return
        existing = Product.query.filter_by(slug=raw).first()
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
