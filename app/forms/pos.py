from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import DecimalField, SelectField, StringField, TextAreaField
from wtforms.validators import DataRequired, Optional

from app.models.inventory import InventoryLocation


class PosSessionForm(FlaskForm):
    opening_cash = DecimalField("Opening Cash", validators=[DataRequired()], default=0)
    market_id = StringField("Market/Event ID", validators=[Optional()])
    inventory_location_id = SelectField("Inventory Location", coerce=int, validators=[Optional()], default=0)
    notes = TextAreaField("Notes", validators=[Optional()])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        locs = InventoryLocation.query.filter_by(active=True).order_by(InventoryLocation.name).all()
        self.inventory_location_id.choices = [(0, "---")] + [(loc.id, loc.name) for loc in locs]


class PosCloseSessionForm(FlaskForm):
    closing_cash = DecimalField("Cash Counted", validators=[DataRequired()], default=0)
    notes = TextAreaField("Notes", validators=[Optional()])
