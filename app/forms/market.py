from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import (
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.fields.datetime import DateField, TimeField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.forms.common import enum_choices
from app.models import Market, MarketPackingList, MarketStatus


class MarketForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=200)])
    location_name = StringField("Location Name", validators=[Optional(), Length(max=200)])
    address = StringField("Address", validators=[Optional(), Length(max=300)])
    city = StringField("City", validators=[Optional(), Length(max=100)])
    state = StringField("State", validators=[Optional(), Length(max=50)])
    event_date = DateField("Event Date", format="%Y-%m-%d", validators=[Optional()])
    start_time = TimeField("Start Time", format="%H:%M", validators=[Optional()])
    end_time = TimeField("End Time", format="%H:%M", validators=[Optional()])
    booth_fee = StringField("Booth Fee", validators=[Optional()])
    application_fee = StringField("Application Fee", validators=[Optional()])
    status = SelectField("Status", choices=enum_choices(MarketStatus), validators=[DataRequired()])
    expected_traffic = StringField("Expected Traffic", validators=[Optional(), Length(max=100)])
    actual_revenue = StringField("Actual Revenue", validators=[Optional()])
    actual_profit = StringField("Actual Profit", validators=[Optional()])
    notes = TextAreaField("Notes", validators=[Optional()])
    submit = SubmitField("Save market")

    def apply(self, market: Market) -> Market:
        market.name = self.name.data.strip()
        market.location_name = self.location_name.data or None
        market.address = self.address.data or None
        market.city = self.city.data or None
        market.state = self.state.data or None
        market.event_date = self.event_date.data
        market.start_time = self.start_time.data
        market.end_time = self.end_time.data
        market.booth_fee = self._parse_money(self.booth_fee.data)
        market.application_fee = self._parse_money(self.application_fee.data)
        market.status = MarketStatus(self.status.data)
        market.expected_traffic = self.expected_traffic.data or None
        market.actual_revenue = self._parse_money(self.actual_revenue.data)
        market.actual_profit = self._parse_money(self.actual_profit.data)
        market.notes = self.notes.data
        return market

    @staticmethod
    def _parse_money(value: str | None) -> int | None:
        if not value:
            return None
        try:
            from decimal import Decimal
            return Decimal(value)
        except (ValueError, TypeError):
            return None


class MarketPackingListForm(FlaskForm):
    product_id = SelectField("Product", coerce=int, validators=[DataRequired()])
    variant_id = SelectField("Variant", coerce=int, validators=[Optional()])
    planned_quantity = IntegerField("Planned Quantity", validators=[Optional(), NumberRange(min=0)], default=0)
    packed_quantity = IntegerField("Packed Quantity", validators=[Optional(), NumberRange(min=0)], default=0)
    sold_quantity = IntegerField("Sold Quantity", validators=[Optional(), NumberRange(min=0)], default=0)
    returned_quantity = IntegerField("Returned Quantity", validators=[Optional(), NumberRange(min=0)], default=0)
    notes = TextAreaField("Notes", validators=[Optional()])
    submit = SubmitField("Save packing list item")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from app.models import Product, ProductVariant
        self.product_id.choices = [
            (p.id, p.name) for p in Product.query.order_by(Product.name)
        ]
        self.variant_id.choices = [(0, "No variant")] + [
            (v.id, f"{v.sku} - {v.name}") for v in ProductVariant.query.order_by(ProductVariant.sku)
        ]

    def apply(self, item: MarketPackingList) -> MarketPackingList:
        item.product_id = self.product_id.data
        item.variant_id = self.variant_id.data or None
        item.planned_quantity = self.planned_quantity.data or 0
        item.packed_quantity = self.packed_quantity.data or 0
        item.sold_quantity = self.sold_quantity.data or 0
        item.returned_quantity = self.returned_quantity.data or 0
        item.notes = self.notes.data
        return item
