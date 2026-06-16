from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import DecimalField, SelectField, TextAreaField
from wtforms.validators import DataRequired, Optional

from app.models import Market, MarketStatus
from app.models.inventory import InventoryLocation


class PosSessionForm(FlaskForm):
    opening_cash = DecimalField("Opening Cash", validators=[DataRequired()], default=0)
    market_id = SelectField("Market/Event", coerce=int, validators=[Optional()], default=0)
    inventory_location_id = SelectField("Inventory Location", coerce=int, validators=[Optional()], default=0)
    notes = TextAreaField("Notes", validators=[Optional()])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        locs = InventoryLocation.query.filter_by(active=True).order_by(InventoryLocation.name).all()
        self.inventory_location_id.choices = [(0, "---")] + [(loc.id, loc.name) for loc in locs]
        markets = (
            Market.query.filter(
                Market.status.in_([MarketStatus.SCHEDULED, MarketStatus.ACCEPTED, MarketStatus.INTERESTED])
            )
            .order_by(Market.event_date.asc())
            .all()
        )
        self.market_id.choices = [(0, "Not at a show / General sale")] + [
            (m.id, f"{m.name} — {m.event_date}" if m.event_date else m.name) for m in markets
        ]


class PosCloseSessionForm(FlaskForm):
    hundreds = DecimalField("$100", validators=[Optional()], default=0)
    fifties = DecimalField("$50", validators=[Optional()], default=0)
    twenties = DecimalField("$20", validators=[Optional()], default=0)
    tens = DecimalField("$10", validators=[Optional()], default=0)
    fives = DecimalField("$5", validators=[Optional()], default=0)
    ones = DecimalField("$1", validators=[Optional()], default=0)
    quarters = DecimalField("$0.25", validators=[Optional()], default=0)
    dimes = DecimalField("$0.10", validators=[Optional()], default=0)
    nickels = DecimalField("$0.05", validators=[Optional()], default=0)
    pennies = DecimalField("$0.01", validators=[Optional()], default=0)
    notes = TextAreaField("Notes", validators=[Optional()])
