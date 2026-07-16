from __future__ import annotations

from decimal import ROUND_HALF_UP

from flask_wtf import FlaskForm
from sqlalchemy import func
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

from app.extensions import db
from app.forms.common import enum_choices
from app.models import (
    InventoryRecord,
    Market,
    MarketDocumentType,
    MarketHotelBooking,
    MarketHotelBookingStatus,
    MarketPackingList,
    MarketStatus,
    MarketTimelineEvent,
    MarketTimelineEventType,
    PrepTask,
    PrepTaskCategory,
    PrepTaskStatus,
    Product,
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
    application_deadline = DateField("Application Deadline", format="%Y-%m-%d", validators=[Optional()])
    application_submitted_at = DateTimeLocalField("Application Submitted", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    application_approved_at = DateTimeLocalField("Application Approved", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    application_url = StringField("Application URL", validators=[Optional(), Length(max=500)])
    application_contact = StringField("Application Contact", validators=[Optional(), Length(max=200)])
    fee_paid_at = DateTimeLocalField("Fee Paid", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    booth_location = StringField("Booth Location", validators=[Optional(), Length(max=160)])
    booth_size = StringField("Booth Size", validators=[Optional(), Length(max=80)])
    booth_rules = TextAreaField("Booth Rules", validators=[Optional()])
    required_documents = TextAreaField("Required Documents", validators=[Optional()])
    power_available = BooleanField("Power Available")
    wifi_available = BooleanField("Wi-Fi Available")
    food_available = BooleanField("Food Available")
    load_in_at = DateTimeLocalField("Load In", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    load_out_at = DateTimeLocalField("Load Out", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    load_in_notes = TextAreaField("Load-In Notes", validators=[Optional()])
    load_out_notes = TextAreaField("Load-Out Notes", validators=[Optional()])
    booth_fee = DecimalField("Booth Fee", places=2, rounding=ROUND_HALF_UP, validators=[Optional()], filters=[lambda x: x or None])
    application_fee = DecimalField("Application Fee", places=2, rounding=ROUND_HALF_UP, validators=[Optional()], filters=[lambda x: x or None])
    status = SelectField("Status", choices=enum_choices(MarketStatus), validators=[DataRequired()])
    expected_traffic = StringField("Expected Traffic", validators=[Optional(), Length(max=100)])
    actual_revenue = DecimalField("Actual Revenue", places=2, rounding=ROUND_HALF_UP, validators=[Optional()], filters=[lambda x: x or None])
    actual_profit = DecimalField("Actual Profit", places=2, rounding=ROUND_HALF_UP, validators=[Optional()], filters=[lambda x: x or None])
    follow_up_date = DateField("Follow-Up Date", format="%Y-%m-%d", validators=[Optional()])
    worth_repeating = SelectField("Worth Repeating", choices=[("", "---"), ("true", "Yes"), ("false", "No")], validators=[Optional()])
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
        market.application_deadline = self.application_deadline.data
        market.application_submitted_at = self.application_submitted_at.data
        market.application_approved_at = self.application_approved_at.data
        market.application_url = self.application_url.data or None
        market.application_contact = self.application_contact.data or None
        market.fee_paid_at = self.fee_paid_at.data
        market.booth_location = self.booth_location.data or None
        market.booth_size = self.booth_size.data or None
        market.booth_rules = self.booth_rules.data
        market.required_documents = self.required_documents.data
        market.power_available = bool(self.power_available.data)
        market.wifi_available = bool(self.wifi_available.data)
        market.food_available = bool(self.food_available.data)
        market.load_in_at = self.load_in_at.data
        market.load_out_at = self.load_out_at.data
        market.load_in_notes = self.load_in_notes.data
        market.load_out_notes = self.load_out_notes.data
        market.booth_fee = self.booth_fee.data
        market.application_fee = self.application_fee.data
        market.status = MarketStatus(self.status.data)
        market.expected_traffic = self.expected_traffic.data or None
        market.actual_revenue = self.actual_revenue.data
        market.actual_profit = self.actual_profit.data
        market.follow_up_date = self.follow_up_date.data
        wr = self.worth_repeating.data
        if wr == "true":
            market.worth_repeating = True
        elif wr == "false":
            market.worth_repeating = False
        else:
            market.worth_repeating = None
        market.notes = self.notes.data
        return market



class MarketPackingListForm(FlaskForm):
    product_id = SelectField("Product", coerce=int, validators=[DataRequired()])
    planned_quantity = IntegerField("Planned Quantity", validators=[Optional(), NumberRange(min=0)], default=0)
    packed_quantity = IntegerField("Packed Quantity", validators=[Optional(), NumberRange(min=0)], default=0)
    sold_quantity = IntegerField("Sold Quantity", validators=[Optional(), NumberRange(min=0)], default=0)
    returned_quantity = IntegerField("Returned Quantity", validators=[Optional(), NumberRange(min=0)], default=0)
    notes = TextAreaField("Notes", validators=[Optional()])
    submit = SubmitField("Save packing list item")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        products = Product.query.order_by(Product.name).all()
        product_ids = [p.id for p in products]
        stock_counts: dict[int, int] = dict(
            db.session.query(
                InventoryRecord.product_id,
                func.coalesce(func.sum(InventoryRecord.quantity_on_hand), 0),
            )
            .filter(InventoryRecord.product_id.in_(product_ids))
            .group_by(InventoryRecord.product_id)
            .all()
        )
        self.product_id.choices = [
            (p.id, f"{p.name}   [{stock_counts.get(p.id, 0)} in stock]")
            for p in products
        ]

    def apply(self, item: MarketPackingList) -> MarketPackingList:
        item.product_id = self.product_id.data
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
    application_deadline = DateField("Application Deadline", format="%Y-%m-%d", validators=[Optional()])
    application_submitted_at = DateTimeLocalField("Application Submitted", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    application_approved_at = DateTimeLocalField("Application Approved", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    application_url = StringField("Application URL", validators=[Optional(), Length(max=500)])
    application_contact = StringField("Application Contact", validators=[Optional(), Length(max=200)])
    fee_paid_at = DateTimeLocalField("Fee Paid", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    booth_rules = TextAreaField("Booth Rules", validators=[Optional()])
    required_documents = TextAreaField("Required Documents", validators=[Optional()])
    load_in_at = DateTimeLocalField("Load In", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    load_out_at = DateTimeLocalField("Load Out", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    load_in_notes = TextAreaField("Load-In Notes", validators=[Optional()])
    load_out_notes = TextAreaField("Load-Out Notes", validators=[Optional()])
    follow_up_date = DateField("Follow-Up Date", format="%Y-%m-%d", validators=[Optional()])
    worth_repeating = SelectField("Worth Repeating", choices=[("", "---"), ("true", "Yes"), ("false", "No")], validators=[Optional()])
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
        market.application_deadline = self.application_deadline.data
        market.application_submitted_at = self.application_submitted_at.data
        market.application_approved_at = self.application_approved_at.data
        market.application_url = self.application_url.data or None
        market.application_contact = self.application_contact.data or None
        market.fee_paid_at = self.fee_paid_at.data
        market.booth_rules = self.booth_rules.data
        market.required_documents = self.required_documents.data
        market.load_in_at = self.load_in_at.data
        market.load_out_at = self.load_out_at.data
        market.load_in_notes = self.load_in_notes.data
        market.load_out_notes = self.load_out_notes.data
        market.follow_up_date = self.follow_up_date.data
        wr = self.worth_repeating.data
        if wr == "true":
            market.worth_repeating = True
        elif wr == "false":
            market.worth_repeating = False
        else:
            market.worth_repeating = None
        return market


class MarketPrepTaskForm(FlaskForm):
    title = StringField("Task", validators=[DataRequired(), Length(max=200)])
    category = SelectField("Category", choices=enum_choices(PrepTaskCategory), validators=[DataRequired()])
    status = SelectField("Status", choices=enum_choices(PrepTaskStatus), validators=[DataRequired()], default=PrepTaskStatus.OPEN.value)
    due_at = DateTimeLocalField("Due", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    notes = TextAreaField("Notes", validators=[Optional()])
    submit = SubmitField("Save task")

    def apply(self, task: PrepTask) -> PrepTask:
        task.title = self.title.data.strip()
        task.category = PrepTaskCategory(self.category.data)
        task.status = PrepTaskStatus(self.status.data)
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
