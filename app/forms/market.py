from __future__ import annotations

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
from wtforms.fields.datetime import DateField, DateTimeLocalField, TimeField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.forms.common import enum_choices
from app.models import (
    Market,
    MarketDocumentType,
    MarketHotelBooking,
    MarketHotelBookingStatus,
    MarketPackingList,
    MarketStatus,
    MarketTask,
    MarketTaskStatus,
    MarketTaskType,
    MarketTimelineEvent,
    MarketTimelineEventType,
)


class MarketForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=200)])
    location_name = StringField("Location Name", validators=[Optional(), Length(max=200)])
    address = StringField("Address", validators=[Optional(), Length(max=300)])
    city = StringField("City", validators=[Optional(), Length(max=100)])
    state = StringField("State", validators=[Optional(), Length(max=50)])
    zip_code = StringField("ZIP Code", validators=[Optional(), Length(max=20)])
    event_date = DateField("Event Date", format="%Y-%m-%d", validators=[Optional()])
    start_time = TimeField("Start Time", format="%H:%M", validators=[Optional()])
    end_time = TimeField("End Time", format="%H:%M", validators=[Optional()])
    application_submitted_at = DateTimeLocalField("Application Submitted", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    application_approved_at = DateTimeLocalField("Application Approved", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    fee_paid_at = DateTimeLocalField("Fee Paid", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    booth_location = StringField("Booth Location", validators=[Optional(), Length(max=160)])
    booth_size = StringField("Booth Size", validators=[Optional(), Length(max=80)])
    power_available = BooleanField("Power Available")
    wifi_available = BooleanField("Wi-Fi Available")
    food_available = BooleanField("Food Available")
    load_in_at = DateTimeLocalField("Load In", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    load_out_at = DateTimeLocalField("Load Out", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    load_in_notes = TextAreaField("Load-In Notes", validators=[Optional()])
    load_out_notes = TextAreaField("Load-Out Notes", validators=[Optional()])
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
        market.zip_code = self.zip_code.data or None
        market.event_date = self.event_date.data
        market.start_time = self.start_time.data
        market.end_time = self.end_time.data
        market.application_submitted_at = self.application_submitted_at.data
        market.application_approved_at = self.application_approved_at.data
        market.fee_paid_at = self.fee_paid_at.data
        market.booth_location = self.booth_location.data or None
        market.booth_size = self.booth_size.data or None
        market.power_available = bool(self.power_available.data)
        market.wifi_available = bool(self.wifi_available.data)
        market.food_available = bool(self.food_available.data)
        market.load_in_at = self.load_in_at.data
        market.load_out_at = self.load_out_at.data
        market.load_in_notes = self.load_in_notes.data
        market.load_out_notes = self.load_out_notes.data
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


class MarketLogisticsForm(FlaskForm):
    location_name = StringField("Location Name", validators=[Optional(), Length(max=200)])
    address = StringField("Address", validators=[Optional(), Length(max=300)])
    city = StringField("City", validators=[Optional(), Length(max=100)])
    state = StringField("State", validators=[Optional(), Length(max=50)])
    zip_code = StringField("ZIP Code", validators=[Optional(), Length(max=20)])
    booth_location = StringField("Booth Location", validators=[Optional(), Length(max=160)])
    booth_size = StringField("Booth Size", validators=[Optional(), Length(max=80)])
    power_available = BooleanField("Power")
    wifi_available = BooleanField("Wi-Fi")
    food_available = BooleanField("Food")
    application_submitted_at = DateTimeLocalField("Application Submitted", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    application_approved_at = DateTimeLocalField("Application Approved", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    fee_paid_at = DateTimeLocalField("Fee Paid", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    load_in_at = DateTimeLocalField("Load In", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    load_out_at = DateTimeLocalField("Load Out", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    load_in_notes = TextAreaField("Load-In Notes", validators=[Optional()])
    load_out_notes = TextAreaField("Load-Out Notes", validators=[Optional()])
    submit = SubmitField("Save logistics")

    def apply(self, market: Market) -> Market:
        market.location_name = self.location_name.data or None
        market.address = self.address.data or None
        market.city = self.city.data or None
        market.state = self.state.data or None
        market.zip_code = self.zip_code.data or None
        market.booth_location = self.booth_location.data or None
        market.booth_size = self.booth_size.data or None
        market.power_available = bool(self.power_available.data)
        market.wifi_available = bool(self.wifi_available.data)
        market.food_available = bool(self.food_available.data)
        market.application_submitted_at = self.application_submitted_at.data
        market.application_approved_at = self.application_approved_at.data
        market.fee_paid_at = self.fee_paid_at.data
        market.load_in_at = self.load_in_at.data
        market.load_out_at = self.load_out_at.data
        market.load_in_notes = self.load_in_notes.data
        market.load_out_notes = self.load_out_notes.data
        return market


class MarketTaskForm(FlaskForm):
    title = StringField("Task", validators=[DataRequired(), Length(max=200)])
    task_type = SelectField("Type", choices=enum_choices(MarketTaskType), validators=[DataRequired()])
    status = SelectField("Status", choices=enum_choices(MarketTaskStatus), validators=[DataRequired()], default=MarketTaskStatus.OPEN.value)
    due_at = DateTimeLocalField("Due", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    notes = TextAreaField("Notes", validators=[Optional()])
    submit = SubmitField("Save task")

    def apply(self, task: MarketTask) -> MarketTask:
        task.title = self.title.data.strip()
        task.task_type = MarketTaskType(self.task_type.data)
        task.status = MarketTaskStatus(self.status.data)
        task.due_at = self.due_at.data
        task.notes = self.notes.data
        return task


class MarketTimelineEventForm(FlaskForm):
    title = StringField("Event", validators=[DataRequired(), Length(max=200)])
    starts_at = DateTimeLocalField("Starts", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    ends_at = DateTimeLocalField("Ends", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    location = StringField("Location", validators=[Optional(), Length(max=200)])
    event_type = SelectField("Type", choices=enum_choices(MarketTimelineEventType), validators=[DataRequired()], default=MarketTimelineEventType.OTHER.value)
    notes = TextAreaField("Notes", validators=[Optional()])
    submit = SubmitField("Save timeline event")

    def apply(self, item: MarketTimelineEvent) -> MarketTimelineEvent:
        item.title = self.title.data.strip()
        item.starts_at = self.starts_at.data
        item.ends_at = self.ends_at.data
        item.location = self.location.data or None
        item.event_type = MarketTimelineEventType(self.event_type.data)
        item.notes = self.notes.data
        return item


class MarketHotelBookingForm(FlaskForm):
    hotel_name = StringField("Hotel", validators=[DataRequired(), Length(max=200)])
    address = StringField("Address", validators=[Optional(), Length(max=300)])
    check_in_date = DateField("Check In", format="%Y-%m-%d", validators=[Optional()])
    check_out_date = DateField("Check Out", format="%Y-%m-%d", validators=[Optional()])
    confirmation_number = StringField("Confirmation", validators=[Optional(), Length(max=120)])
    cost = DecimalField("Cost", places=2, validators=[Optional()])
    status = SelectField("Status", choices=enum_choices(MarketHotelBookingStatus), validators=[DataRequired()], default=MarketHotelBookingStatus.PLANNED.value)
    notes = TextAreaField("Notes", validators=[Optional()])
    submit = SubmitField("Save hotel")

    def apply(self, booking: MarketHotelBooking) -> MarketHotelBooking:
        booking.hotel_name = self.hotel_name.data.strip()
        booking.address = self.address.data or None
        booking.check_in_date = self.check_in_date.data
        booking.check_out_date = self.check_out_date.data
        booking.confirmation_number = self.confirmation_number.data or None
        booking.cost = self.cost.data
        booking.status = MarketHotelBookingStatus(self.status.data)
        booking.notes = self.notes.data
        return booking


class MarketDocumentForm(FlaskForm):
    document_type = SelectField("Document Type", choices=enum_choices(MarketDocumentType), validators=[DataRequired()], default=MarketDocumentType.OTHER.value)
    notes = TextAreaField("Notes", validators=[Optional()])
    submit = SubmitField("Upload document")
