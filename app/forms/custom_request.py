from __future__ import annotations

from decimal import Decimal

from flask_wtf import FlaskForm
from wtforms import DecimalField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.fields.datetime import DateTimeLocalField
from wtforms.validators import DataRequired, Length, Optional

from app.forms.common import enum_choices
from app.models import CustomRequest, CustomRequestStatus


class CustomRequestForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=200)])
    email = StringField("Email", validators=[DataRequired(), Length(max=255)])
    phone = StringField("Phone", validators=[Optional(), Length(max=50)])
    description = TextAreaField("Description", validators=[DataRequired()])
    estimated_budget = StringField("Estimated Budget", validators=[Optional()])
    deadline = DateTimeLocalField(
        "Deadline", format="%Y-%m-%dT%H:%M", validators=[Optional()]
    )
    status = SelectField(
        "Status", choices=enum_choices(CustomRequestStatus), validators=[DataRequired()]
    )
    subtotal = DecimalField("Subtotal", validators=[Optional()], places=2, default=0)
    tax = DecimalField("Tax", validators=[Optional()], places=2, default=0)
    discount = DecimalField("Discount", validators=[Optional()], places=2, default=0)
    total = DecimalField("Total", validators=[Optional()], places=2, default=0)
    amount_paid = DecimalField("Amount Paid", validators=[Optional()], places=2, default=0)
    admin_notes = TextAreaField("Admin Notes", validators=[Optional()])
    internal_notes = TextAreaField("Internal Notes", validators=[Optional()])
    submit = SubmitField("Save custom request")

    def apply(self, request: CustomRequest) -> CustomRequest:
        request.name = self.name.data.strip()
        request.email = self.email.data.strip()
        request.phone = self.phone.data.strip() if self.phone.data else None
        request.description = self.description.data
        request.estimated_budget = self.estimated_budget.data
        request.deadline = self.deadline.data
        request.status = CustomRequestStatus(self.status.data)
        request.subtotal = self.subtotal.data
        request.tax = self.tax.data or Decimal(0)
        request.discount = self.discount.data or Decimal(0)
        request.total = self.total.data
        request.amount_paid = self.amount_paid.data or Decimal(0)
        request.admin_notes = self.admin_notes.data
        request.internal_notes = self.internal_notes.data
        return request


class PublicCustomRequestForm(FlaskForm):
    name = StringField("Your Name", validators=[DataRequired(), Length(max=200)])
    email = StringField("Your Email", validators=[DataRequired(), Length(max=255)])
    phone = StringField("Phone (optional)", validators=[Optional(), Length(max=50)])
    description = TextAreaField(
        "Tell us what you'd like us to make",
        validators=[DataRequired()],
        description="Describe your idea: what it is, approximate size, colors, any reference images or links.",
    )
    estimated_budget = StringField("Approximate Budget (optional)", validators=[Optional()])
    submit = SubmitField("Send Request")
