from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.fields.datetime import DateTimeLocalField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError

from app.forms.common import OptionalSelectField, enum_choices
from app.models import AMSUnit, AMSUnitStatus, AMSUnitType, Printer, PrinterStatus


class PrinterForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=160)])
    model = StringField("Model", validators=[DataRequired(), Length(max=160)])
    serial_number = StringField("Serial Number", validators=[Optional(), Length(max=120)])
    status = SelectField("Status", choices=enum_choices(PrinterStatus), validators=[DataRequired()])
    location = StringField("Location", validators=[Optional(), Length(max=160)])
    has_ams = BooleanField("Has AMS", default=False)
    default_nozzle_size = StringField(
        "Default Nozzle Size", validators=[Optional(), Length(max=50)]
    )
    notes = TextAreaField("Notes", validators=[Optional()])
    purchase_date = DateTimeLocalField(
        "Purchase Date", format="%Y-%m-%dT%H:%M", validators=[Optional()]
    )
    maintenance_notes = TextAreaField("Maintenance Notes", validators=[Optional()])
    total_print_hours = IntegerField(
        "Total Print Hours", validators=[Optional(), NumberRange(min=0)], default=0
    )
    submit = SubmitField("Save printer")

    def validate_name(self, field):
        existing = Printer.query.filter_by(name=field.data.strip()).first()
        if existing and getattr(self, "instance_id", None) != existing.id:
            raise ValidationError("A printer with that name already exists.")

    def apply(self, printer: Printer) -> Printer:
        printer.name = self.name.data.strip()
        printer.model = self.model.data.strip()
        printer.serial_number = self.serial_number.data or None
        printer.status = PrinterStatus(self.status.data)
        printer.location = self.location.data or None
        printer.has_ams = bool(self.has_ams.data)
        printer.default_nozzle_size = self.default_nozzle_size.data or None
        printer.notes = self.notes.data
        printer.purchase_date = self.purchase_date.data
        printer.maintenance_notes = self.maintenance_notes.data
        printer.total_print_hours = self.total_print_hours.data or 0
        return printer


class AMSUnitForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=160)])
    type = SelectField("Type", choices=enum_choices(AMSUnitType), validators=[DataRequired()])
    status = SelectField("Status", choices=enum_choices(AMSUnitStatus), validators=[DataRequired()])
    assigned_printer_id = OptionalSelectField(
        "Assigned Printer", coerce=int, validators=[Optional()]
    )
    slot_count = IntegerField("Slot Count", validators=[Optional(), NumberRange(min=1)], default=4)
    notes = TextAreaField("Notes", validators=[Optional()])
    submit = SubmitField("Save AMS unit")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.assigned_printer_id.choices = [(0, "Not assigned")] + [
            (item.id, item.name) for item in Printer.query.order_by(Printer.name)
        ]

    def validate_name(self, field):
        existing = AMSUnit.query.filter_by(name=field.data.strip()).first()
        if existing and getattr(self, "instance_id", None) != existing.id:
            raise ValidationError("An AMS unit with that name already exists.")

    def apply(self, ams_unit: AMSUnit) -> AMSUnit:
        ams_unit.name = self.name.data.strip()
        ams_unit.type = AMSUnitType(self.type.data)
        ams_unit.status = AMSUnitStatus(self.status.data)
        ams_unit.assigned_printer_id = self.assigned_printer_id.data or None
        ams_unit.slot_count = self.slot_count.data or 4
        ams_unit.notes = self.notes.data
        return ams_unit
