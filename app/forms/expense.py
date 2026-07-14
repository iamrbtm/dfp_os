from __future__ import annotations

from decimal import ROUND_HALF_UP

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DecimalField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.fields.datetime import DateField
from wtforms.validators import DataRequired, Length, Optional

from app.extensions import db
from app.forms.common import enum_choices
from app.models import CustomRequest, CustomRequestStatus, Expense, ExpenseCategory, Market, MarketStatus


class ExpenseForm(FlaskForm):
    date = DateField("Date", format="%Y-%m-%d", validators=[DataRequired()])
    vendor = StringField("Vendor", validators=[DataRequired(), Length(max=200)])
    category = SelectField(
        "Category", choices=enum_choices(ExpenseCategory), validators=[DataRequired()]
    )
    description = TextAreaField("Description", validators=[Optional()])
    amount = DecimalField("Amount", places=2, rounding=ROUND_HALF_UP, validators=[DataRequired()])
    payment_method = StringField("Payment Method", validators=[Optional(), Length(max=100)])
    related_market_id = SelectField("Market", coerce=int, validators=[Optional()], default=0)
    related_order_id = SelectField("Custom Order", coerce=int, validators=[Optional()], default=0)
    receipt_file_path = StringField("Receipt File", validators=[Optional(), Length(max=300)])
    tax_deductible = BooleanField("Tax Deductible", default=False)
    notes = TextAreaField("Notes", validators=[Optional()])
    submit = SubmitField("Save expense")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        markets = (
            Market.query.filter(
                ~Market.status.in_([MarketStatus.COMPLETED, MarketStatus.CANCELED, MarketStatus.NOT_WORTH_REPEATING])
            )
            .order_by(Market.event_date.asc())
            .all()
        )
        self.related_market_id.choices = [(0, "— None —")] + [
            (m.id, f"{m.name} — {m.event_date}" if m.event_date else m.name) for m in markets
        ]
        current_market = self.related_market_id.data
        existing_ids = {c[0] for c in self.related_market_id.choices}
        if current_market and current_market not in existing_ids:
            m = db.session.get(Market, current_market)
            if m:
                self.related_market_id.choices.append(
                    (m.id, f"{m.name} — {m.event_date}" if m.event_date else m.name)
                )

        open_orders = (
            CustomRequest.query.filter(
                ~CustomRequest.status.in_([CustomRequestStatus.COMPLETED, CustomRequestStatus.CANCELLED, CustomRequestStatus.ARCHIVED])
            )
            .order_by(CustomRequest.created_at.desc())
            .all()
        )
        self.related_order_id.choices = [(0, "— None —")] + [
            (r.id, f"#{r.id} — {r.name[:60]}" if r.name else f"#{r.id}") for r in open_orders
        ]
        current_order = self.related_order_id.data
        existing_ids = {c[0] for c in self.related_order_id.choices}
        if current_order and current_order not in existing_ids:
            r = db.session.get(CustomRequest, current_order)
            if r:
                label = f"#{r.id} — {r.name[:60]}" if r.name else f"#{r.id}"
                self.related_order_id.choices.append((r.id, label))

    def apply(self, expense: Expense) -> Expense:
        expense.date = self.date.data
        expense.vendor = self.vendor.data.strip()
        expense.category = ExpenseCategory(self.category.data)
        expense.description = self.description.data
        expense.amount = self.amount.data
        expense.payment_method = self.payment_method.data or None
        expense.related_market_id = self.related_market_id.data or None if self.related_market_id.data else None
        expense.related_order_id = self.related_order_id.data or None if self.related_order_id.data else None
        expense.receipt_file_path = self.receipt_file_path.data or None
        expense.tax_deductible = bool(self.tax_deductible.data)
        expense.notes = self.notes.data
        return expense

