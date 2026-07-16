from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.fields.datetime import DateTimeLocalField
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.forms.common import OptionalSelectField, enum_choices
from app.models import Market, PickupLocation, PickupLocationType, PickupSlot, PickupSlotStatus


class PickupLocationForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=160)])
    location_type = SelectField("Type", choices=enum_choices(PickupLocationType), validators=[DataRequired()])
    address = StringField("Address", validators=[Optional(), Length(max=255)])
    instructions = TextAreaField("Instructions", validators=[Optional()])
    active = BooleanField("Active", default=True)
    submit = SubmitField("Save pickup location")

    def apply(self, location: PickupLocation) -> PickupLocation:
        location.name = self.name.data.strip()
        location.location_type = PickupLocationType(self.location_type.data)
        location.address = self.address.data.strip() if self.address.data else None
        location.instructions = self.instructions.data
        location.active = bool(self.active.data)
        return location


class PickupSlotForm(FlaskForm):
    location_id = SelectField("Location", coerce=int, validators=[DataRequired()])
    market_id = OptionalSelectField("Market", coerce=int, validators=[Optional()])
    starts_at = DateTimeLocalField("Starts at", format="%Y-%m-%dT%H:%M", validators=[DataRequired()])
    ends_at = DateTimeLocalField("Ends at", format="%Y-%m-%dT%H:%M", validators=[DataRequired()])
    capacity = IntegerField("Capacity", validators=[DataRequired(), NumberRange(min=1)], default=6)
    status = SelectField("Status", choices=enum_choices(PickupSlotStatus), validators=[DataRequired()])
    public_label = StringField("Public label", validators=[Optional(), Length(max=200)])
    instructions = TextAreaField("Slot instructions", validators=[Optional()])
    submit = SubmitField("Save pickup slot")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.location_id.choices = [
            (item.id, item.name) for item in PickupLocation.query.filter_by(active=True).order_by(PickupLocation.name)
        ]
        self.market_id.choices = [(0, "No market")] + [
            (item.id, item.name) for item in Market.query.order_by(Market.event_date.desc(), Market.name)
        ]

    def validate(self, extra_validators=None):
        is_valid = super().validate(extra_validators=extra_validators)
        if not is_valid:
            return False
        if self.starts_at.data and self.ends_at.data and self.ends_at.data <= self.starts_at.data:
            self.ends_at.errors.append("End time must be after start time.")
            return False
        return True

    def apply(self, slot: PickupSlot) -> PickupSlot:
        slot.location_id = self.location_id.data
        slot.market_id = self.market_id.data or None
        slot.starts_at = self.starts_at.data
        slot.ends_at = self.ends_at.data
        slot.capacity = self.capacity.data or 1
        slot.status = PickupSlotStatus(self.status.data)
        slot.public_label = self.public_label.data.strip() if self.public_label.data else None
        slot.instructions = self.instructions.data
        return slot
