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
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError

from app.forms.common import decimal_or_zero, enum_choices
from app.models import (
    FilamentSpool,
    FilamentStatus,
    InventoryLocation,
    InventoryRecord,
    Product,
)


class FilamentSpoolForm(FlaskForm):
    brand = StringField("Brand", validators=[DataRequired(), Length(max=160)])
    material_type = StringField("Material Type", validators=[DataRequired(), Length(max=120)])
    color_name = StringField("Color Name", validators=[DataRequired(), Length(max=120)])
    color_hex = StringField("Color Hex", validators=[Optional(), Length(max=7)])
    spool_weight_grams = IntegerField(
        "Spool Weight (g)", validators=[Optional(), NumberRange(min=0)], default=1000
    )
    remaining_weight_grams = IntegerField(
        "Remaining Weight (g)", validators=[Optional(), NumberRange(min=0)], default=1000
    )
    cost_per_spool = DecimalField(
        "Cost Per Spool", places=2, validators=[Optional(), NumberRange(min=0)]
    )
    cost_per_gram = DecimalField(
        "Cost Per Gram", places=4, validators=[Optional(), NumberRange(min=0)]
    )
    supplier = StringField("Supplier", validators=[Optional(), Length(max=160)])
    purchase_date = DateTimeLocalField(
        "Purchase Date", format="%Y-%m-%dT%H:%M", validators=[Optional()]
    )
    storage_location = StringField("Storage Location", validators=[Optional(), Length(max=160)])
    status = SelectField(
        "Status", choices=enum_choices(FilamentStatus), validators=[DataRequired()]
    )
    reorder_threshold_grams = IntegerField(
        "Reorder Threshold (g)", validators=[Optional(), NumberRange(min=0)], default=150
    )
    notes = TextAreaField("Notes", validators=[Optional()])
    submit = SubmitField("Save filament spool")

    def apply(self, spool: FilamentSpool) -> FilamentSpool:
        spool.brand = self.brand.data.strip()
        spool.material_type = self.material_type.data.strip()
        spool.color_name = self.color_name.data.strip()
        spool.color_hex = self.color_hex.data or None
        spool.spool_weight_grams = self.spool_weight_grams.data or 0
        spool.remaining_weight_grams = self.remaining_weight_grams.data or 0
        spool.cost_per_spool = decimal_or_zero(self.cost_per_spool.data)
        spool.cost_per_gram = self.cost_per_gram.data or Decimal("0")
        spool.supplier = self.supplier.data or None
        spool.purchase_date = self.purchase_date.data
        spool.storage_location = self.storage_location.data or None
        spool.status = FilamentStatus(self.status.data)
        spool.reorder_threshold_grams = self.reorder_threshold_grams.data or 0
        spool.notes = self.notes.data
        return spool


class InventoryLocationForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=160)])
    type = StringField("Type", validators=[DataRequired(), Length(max=120)])
    description = TextAreaField("Description", validators=[Optional()])
    active = BooleanField("Active", default=True)
    submit = SubmitField("Save location")

    def validate_name(self, field):
        existing = InventoryLocation.query.filter_by(name=field.data.strip()).first()
        if existing and getattr(self, "instance_id", None) != existing.id:
            raise ValidationError("An inventory location with that name already exists.")

    def apply(self, location: InventoryLocation) -> InventoryLocation:
        location.name = self.name.data.strip()
        location.type = self.type.data.strip()
        location.description = self.description.data
        location.active = bool(self.active.data)
        return location


class InventoryRecordForm(FlaskForm):
    product_id = SelectField("Product", coerce=int, validators=[DataRequired()])
    location_id = SelectField("Location", coerce=int, validators=[DataRequired()])
    quantity_on_hand = IntegerField(
        "Quantity On Hand", validators=[Optional(), NumberRange(min=0)], default=0
    )
    quantity_reserved = IntegerField(
        "Quantity Reserved", validators=[Optional(), NumberRange(min=0)], default=0
    )
    reorder_threshold = IntegerField(
        "Reorder Threshold", validators=[Optional(), NumberRange(min=0)], default=0
    )
    reorder_target = IntegerField(
        "Reorder Target", validators=[Optional(), NumberRange(min=0)], default=0
    )
    last_counted_at = DateTimeLocalField(
        "Last Counted At", format="%Y-%m-%dT%H:%M", validators=[Optional()]
    )
    submit = SubmitField("Save inventory record")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.product_id.choices = [
            (item.id, item.name) for item in Product.query.order_by(Product.name)
        ]
        self.location_id.choices = [
            (item.id, item.name)
            for item in InventoryLocation.query.order_by(InventoryLocation.name)
        ]

    def apply(self, record: InventoryRecord) -> InventoryRecord:
        record.product_id = self.product_id.data
        record.location_id = self.location_id.data
        record.quantity_on_hand = self.quantity_on_hand.data or 0
        record.quantity_reserved = self.quantity_reserved.data or 0
        record.reorder_threshold = self.reorder_threshold.data or 0
        record.reorder_target = self.reorder_target.data or 0
        record.last_counted_at = self.last_counted_at.data
        return record


class InventoryAdjustmentForm(FlaskForm):
    quantity_delta = IntegerField("Adjustment Quantity", validators=[DataRequired()])
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=1000)])
    submit = SubmitField("Apply adjustment")


class InventoryTransferForm(FlaskForm):
    to_location_id = SelectField("Transfer To", coerce=int, validators=[DataRequired()])
    quantity = IntegerField("Quantity", validators=[DataRequired(), NumberRange(min=1)])
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=1000)])
    submit = SubmitField("Transfer inventory")

    def __init__(self, *args, source_location_id: int | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        query = InventoryLocation.query.filter(InventoryLocation.active.is_(True)).order_by(InventoryLocation.name)
        if source_location_id is not None:
            query = query.filter(InventoryLocation.id != source_location_id)
        self.to_location_id.choices = [(item.id, item.name) for item in query]


class InventoryReservationForm(FlaskForm):
    quantity = IntegerField("Quantity", validators=[DataRequired(), NumberRange(min=1)])
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=1000)])
    submit_reserve = SubmitField("Reserve stock")
    submit_release = SubmitField("Release stock")
