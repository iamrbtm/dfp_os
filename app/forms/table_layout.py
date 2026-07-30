from __future__ import annotations

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import BooleanField, IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.models import Product


class MarketTableLayoutForm(FlaskForm):
    name = StringField("Layout Name", validators=[DataRequired(), Length(max=200)])
    notes = TextAreaField("Notes", validators=[Optional()])
    photo = FileField("Layout Photo", validators=[Optional(), FileAllowed(["jpg", "jpeg", "png", "webp"], "Images only (jpg, png, webp).")])
    is_template = BooleanField("Save as Template")
    submit = SubmitField("Save Layout")



class MarketTablePlacementForm(FlaskForm):
    product_id = SelectField("Product", coerce=int, validators=[DataRequired()])
    quantity = IntegerField("Quantity", default=1, validators=[DataRequired(), NumberRange(min=1)])
    sort_order = IntegerField("Sort Order", default=0, validators=[Optional()])
    notes = StringField("Notes", validators=[Optional(), Length(max=500)])
    submit = SubmitField("Add Product")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.product_id.choices = [
            (p.id, f"{p.name} (${float(p.base_price or 0):.2f})")
            for p in Product.query.order_by(Product.name).all()
        ]
