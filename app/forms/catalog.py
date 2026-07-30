from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, IntegerField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError

from app.models import Category, Collection
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



