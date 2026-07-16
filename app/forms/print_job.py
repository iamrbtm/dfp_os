from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.fields.datetime import DateTimeLocalField
from wtforms.validators import NumberRange, Optional

from app.forms.common import OptionalSelectField, enum_choices
from app.models import (
    FilamentSpool,
    PrintFailureAutopsy,
    PrintFailureCategory,
    PrintFailureSeverity,
    PrintJob,
    PrintJobStatus,
    Printer,
    Product,
    User,
)


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


class PrintFailureAutopsyForm(FlaskForm):
    category = SelectField(
        "Failure Category",
        choices=enum_choices(PrintFailureCategory),
        validators=[Optional()],
    )
    severity = SelectField(
        "Severity",
        choices=enum_choices(PrintFailureSeverity),
        validators=[Optional()],
    )
    filament_spool_id = OptionalSelectField("Filament Spool", coerce=int, validators=[Optional()])
    model_asset_id = IntegerField("Model Asset ID", validators=[Optional(), NumberRange(min=1)])
    notes = TextAreaField("What happened?", validators=[Optional()])
    photo_reference = StringField("Photo or File Reference", validators=[Optional()])
    corrective_action = TextAreaField("Corrective Action", validators=[Optional()])
    maintenance_required = BooleanField("Maintenance Required")
    resolved = BooleanField("Resolved")
    resolution_notes = TextAreaField("Resolution Notes", validators=[Optional()])
    submit = SubmitField("Save failure autopsy")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filament_spool_id.choices = [(0, "No filament spool")] + [
            (item.id, f"{item.brand} {item.material_type} {item.color_name}")
            for item in FilamentSpool.query.order_by(
                FilamentSpool.brand, FilamentSpool.material_type, FilamentSpool.color_name
            )
        ]

    def apply(self, autopsy: PrintFailureAutopsy) -> PrintFailureAutopsy:
        autopsy.category = (
            PrintFailureCategory(self.category.data)
            if self.category.data
            else PrintFailureCategory.UNKNOWN
        )
        autopsy.severity = (
            PrintFailureSeverity(self.severity.data)
            if self.severity.data
            else PrintFailureSeverity.MEDIUM
        )
        autopsy.filament_spool_id = self.filament_spool_id.data or None
        autopsy.model_asset_id = self.model_asset_id.data
        autopsy.notes = self.notes.data
        autopsy.photo_reference = self.photo_reference.data
        autopsy.corrective_action = self.corrective_action.data
        autopsy.maintenance_required = bool(self.maintenance_required.data)
        autopsy.resolved = bool(self.resolved.data)
        autopsy.resolution_notes = self.resolution_notes.data
        return autopsy
