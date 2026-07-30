from __future__ import annotations

from decimal import ROUND_HALF_UP

from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms import (
    DecimalField,
    SelectField,
    SelectMultipleField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.fields.datetime import DateTimeField
from wtforms.validators import DataRequired, Length, Optional

from app.forms.common import enum_choices
from app.models.receipt import ReceiptStatus, ReceiptSourceType


class ReceiptUploadForm(FlaskForm):
    files = FileField(
        "Receipt Images or PDFs",
        validators=[DataRequired()],
        render_kw={"multiple": True, "accept": "image/jpeg,image/png,image/heic,image/heif,application/pdf"},
    )
    source_type = SelectField(
        "Source", choices=enum_choices(ReceiptSourceType), default="upload"
    )
    submit = SubmitField("Upload Receipts")


class ReceiptReviewForm(FlaskForm):
    merchant_name = StringField("Merchant", validators=[Optional(), Length(max=255)])
    store_name = StringField("Store Name", validators=[Optional(), Length(max=255)])
    store_number = StringField("Store #", validators=[Optional(), Length(max=40)])
    address_line_1 = StringField("Address", validators=[Optional(), Length(max=255)])
    address_line_2 = StringField("Address 2", validators=[Optional(), Length(max=255)])
    city = StringField("City", validators=[Optional(), Length(max=120)])
    state = StringField("State", validators=[Optional(), Length(max=60)])
    postal_code = StringField("Postal Code", validators=[Optional(), Length(max=20)])
    phone = StringField("Phone", validators=[Optional(), Length(max=50)])
    receipt_number = StringField("Receipt #", validators=[Optional(), Length(max=80)])
    transaction_number = StringField("Transaction #", validators=[Optional(), Length(max=80)])
    date_time = DateTimeField("Date/Time", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    subtotal = DecimalField("Subtotal", places=2, rounding=ROUND_HALF_UP, validators=[Optional()], filters=[lambda x: x or None])
    tax_total = DecimalField("Tax Total", places=2, rounding=ROUND_HALF_UP, validators=[Optional()], filters=[lambda x: x or None])
    fee_total = DecimalField("Fee Total", places=2, rounding=ROUND_HALF_UP, validators=[Optional()], filters=[lambda x: x or None])
    discount_total = DecimalField("Discount Total", places=2, rounding=ROUND_HALF_UP, validators=[Optional()], filters=[lambda x: x or None])
    tip_total = DecimalField("Tip Total", places=2, rounding=ROUND_HALF_UP, validators=[Optional()], filters=[lambda x: x or None])
    deposit_total = DecimalField("Deposit Total", places=2, rounding=ROUND_HALF_UP, validators=[Optional()], filters=[lambda x: x or None])
    grand_total = DecimalField("Grand Total", places=2, rounding=ROUND_HALF_UP, validators=[Optional()], filters=[lambda x: x or None])
    payment_method = StringField("Payment Method", validators=[Optional(), Length(max=60)])
    currency = StringField("Currency", validators=[Optional(), Length(max=3)], default="USD")
    notes = TextAreaField("Notes", validators=[Optional()])
    submit_approve = SubmitField("Approve Receipt")
    submit_reject = SubmitField("Reject Receipt")
    submit_draft = SubmitField("Save Draft")



class ReceiptAllocationForm(FlaskForm):
    line_item_ids = SelectMultipleField("Line Items", coerce=int, validators=[DataRequired()])
    allocation_type = SelectField(
        "Assign To",
        choices=[
            ("", "— Select —"),
            ("market", "Market"),
            ("custom_job", "Custom Job"),
            ("inventory", "Inventory"),
            ("general_expense", "General Business Expense"),
            ("personal_excluded", "Personal/Excluded"),
        ],
        validators=[DataRequired()],
    )
    market_id = SelectField("Market", coerce=int, validators=[Optional()], default=0)
    custom_job_id = SelectField("Custom Job", coerce=int, validators=[Optional()], default=0)
    submit = SubmitField("Assign Items")


class ReceiptSearchForm(FlaskForm):
    q = StringField("Search", validators=[Optional()])
    status = SelectField(
        "Status",
        choices=[("", "All")] + [(s.value, s.value.replace("_", " ").title()) for s in ReceiptStatus],
        validators=[Optional()],
    )
    submit = SubmitField("Filter")
