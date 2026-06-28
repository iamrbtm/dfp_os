from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.fields.datetime import DateTimeLocalField
from wtforms.validators import NumberRange, Optional

from app.forms.common import OptionalSelectField, enum_choices
from app.models import PrintJob, PrintJobStatus, Printer, Product, User


class PrintJobForm(FlaskForm):
    order_item_id = OptionalSelectField("Order Item", coerce=int, validators=[Optional()])
    product_id = OptionalSelectField("Product", coerce=int, validators=[Optional()])
    printer_id = OptionalSelectField("Printer", coerce=int, validators=[Optional()])
    assigned_to_id = OptionalSelectField("Assigned To", coerce=int, validators=[Optional()])
    status = SelectField(
        "Status", choices=enum_choices(PrintJobStatus), validators=[Optional()]
    )
    priority = IntegerField("Priority", validators=[Optional(), NumberRange(min=0)], default=0)
    estimated_minutes = IntegerField(
        "Estimated Minutes", validators=[Optional(), NumberRange(min=0)], default=0
    )
    actual_minutes = IntegerField("Actual Minutes", validators=[Optional(), NumberRange(min=0)])
    filament_used_grams = IntegerField(
        "Filament Used (g)", validators=[Optional(), NumberRange(min=0)]
    )
    failure_reason = TextAreaField("Failure Reason", validators=[Optional()])
    notes = TextAreaField("Notes", validators=[Optional()])
    label = StringField("Label", validators=[Optional()])
    started_at = DateTimeLocalField(
        "Started At", format="%Y-%m-%dT%H:%M", validators=[Optional()]
    )
    completed_at = DateTimeLocalField(
        "Completed At", format="%Y-%m-%dT%H:%M", validators=[Optional()]
    )
    submit = SubmitField("Save print job")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.product_id.choices = [(0, "No product")] + [
            (item.id, item.name) for item in Product.query.order_by(Product.name)
        ]
        self.printer_id.choices = [(0, "No printer")] + [
            (item.id, item.name) for item in Printer.query.order_by(Printer.name)
        ]
        self.assigned_to_id.choices = [(0, "Unassigned")] + [
            (item.id, item.full_name) for item in User.query.order_by(User.first_name)
        ]

    def apply(self, job: PrintJob) -> PrintJob:
        job.product_id = self.product_id.data or None
        job.printer_id = self.printer_id.data or None
        job.assigned_to_id = self.assigned_to_id.data or None
        job.status = PrintJobStatus(self.status.data) if self.status.data else PrintJobStatus.QUEUED
        job.priority = self.priority.data or 0
        job.estimated_minutes = self.estimated_minutes.data or 0
        job.actual_minutes = self.actual_minutes.data
        job.filament_used_grams = self.filament_used_grams.data
        job.failure_reason = self.failure_reason.data
        job.notes = self.notes.data
        job.label = self.label.data
        job.started_at = self.started_at.data
        job.completed_at = self.completed_at.data
        return job
