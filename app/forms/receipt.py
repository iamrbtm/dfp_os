from __future__ import annotations

from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms import (
    BooleanField,
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
    subtotal = StringField("Subtotal", validators=[Optional()])
    tax_total = StringField("Tax Total", validators=[Optional()])
    fee_total = StringField("Fee Total", validators=[Optional()])
    discount_total = StringField("Discount Total", validators=[Optional()])
    tip_total = StringField("Tip Total", validators=[Optional()])
    deposit_total = StringField("Deposit Total", validators=[Optional()])
    grand_total = StringField("Grand Total", validators=[Optional()])
    payment_method = StringField("Payment Method", validators=[Optional(), Length(max=60)])
    currency = StringField("Currency", validators=[Optional(), Length(max=3)], default="USD")
    notes = TextAreaField("Notes", validators=[Optional()])
    submit_approve = SubmitField("Approve Receipt")
    submit_reject = SubmitField("Reject Receipt")
    submit_draft = SubmitField("Save Draft")


class ReceiptLineItemForm(FlaskForm):
    description = StringField("Description", validators=[Optional(), Length(max=500)])
    sku = StringField("SKU", validators=[Optional(), Length(max=100)])
    quantity = StringField("Quantity", validators=[Optional()])
    unit_price = StringField("Unit Price", validators=[Optional()])
    line_total = StringField("Line Total", validators=[Optional()])
    line_discount = StringField("Discount", validators=[Optional()])
    line_tax = StringField("Tax", validators=[Optional()])
    taxable_status = SelectField(
        "Taxable",
        choices=[("unknown", "Unknown"), ("taxable", "Taxable"), ("non_taxable", "Non-Taxable")],
        default="unknown",
    )
    is_inventory_candidate = BooleanField("Inventory Candidate")
    is_personal_or_excluded = BooleanField("Personal/Excluded")
    notes = TextAreaField("Notes", validators=[Optional()])
    submit = SubmitField("Save Line Item")


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
