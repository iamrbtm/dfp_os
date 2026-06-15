from __future__ import annotations

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
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.forms.common import OptionalSelectField, decimal_or_zero, enum_choices
from app.models import Customer, Order, OrderItem, OrderSource, OrderStatus, Payment, PaymentMethod, Product, ProductVariant


class OrderForm(FlaskForm):
    customer_id = OptionalSelectField("Customer", coerce=int, validators=[Optional()])
    status = SelectField(
        "Status", choices=enum_choices(OrderStatus), validators=[DataRequired()]
    )
    source = SelectField(
        "Source", choices=enum_choices(OrderSource), validators=[DataRequired()]
    )
    notes = TextAreaField("Notes", validators=[Optional()])
    internal_notes = TextAreaField("Internal Notes", validators=[Optional()])
    subtotal = DecimalField("Subtotal", places=2, validators=[Optional()])
    tax_total = DecimalField("Tax", places=2, validators=[Optional()])
    discount_total = DecimalField("Discount", places=2, validators=[Optional()])
    total = DecimalField("Total", places=2, validators=[Optional()])
    paid_amount = DecimalField("Paid Amount", places=2, validators=[Optional()])
    submit = SubmitField("Save order")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.customer_id.choices = [(0, "No customer")] + [
            (item.id, f"{item.full_name} ({item.email or 'no email'})")
            for item in Customer.query.order_by(Customer.last_name, Customer.first_name)
        ]

    def apply(self, order: Order) -> Order:
        order.customer_id = self.customer_id.data or None
        order.status = OrderStatus(self.status.data)
        order.source = OrderSource(self.source.data)
        order.notes = self.notes.data
        order.internal_notes = self.internal_notes.data
        order.subtotal = decimal_or_zero(self.subtotal.data)
        order.tax_total = decimal_or_zero(self.tax_total.data)
        order.discount_total = decimal_or_zero(self.discount_total.data)
        order.total = decimal_or_zero(self.total.data)
        order.paid_amount = decimal_or_zero(self.paid_amount.data)
        return order


class OrderItemForm(FlaskForm):
    product_id = OptionalSelectField("Product", coerce=int, validators=[Optional()])
    variant_id = OptionalSelectField("Variant", coerce=int, validators=[Optional()])
    quantity = IntegerField("Quantity", validators=[Optional(), NumberRange(min=1)], default=1)
    unit_price = DecimalField("Unit Price", places=2, validators=[Optional()])
    line_total = DecimalField("Line Total", places=2, validators=[Optional()])
    is_custom_item = BooleanField("Custom Item", default=False)
    custom_description = TextAreaField("Custom Description", validators=[Optional()])
    notes = TextAreaField("Notes", validators=[Optional()])
    submit = SubmitField("Save item")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.product_id.choices = [(0, "No product")] + [
            (item.id, item.name) for item in Product.query.order_by(Product.name)
        ]
        self.variant_id.choices = [(0, "No variant")] + [
            (item.id, f"{item.product.name} · {item.name}")
            for item in ProductVariant.query.join(Product).order_by(
                Product.name, ProductVariant.name
            )
        ]

    def apply(self, item: OrderItem) -> OrderItem:
        item.product_id = self.product_id.data or None
        item.variant_id = self.variant_id.data or None
        item.quantity = self.quantity.data or 1
        item.unit_price = decimal_or_zero(self.unit_price.data)
        item.line_total = decimal_or_zero(self.line_total.data)
        item.is_custom_item = bool(self.is_custom_item.data)
        item.custom_description = self.custom_description.data
        item.notes = self.notes.data
        return item


class PaymentForm(FlaskForm):
    amount = DecimalField("Amount", places=2, validators=[DataRequired(), NumberRange(min=0)])
    method = SelectField(
        "Method", choices=enum_choices(PaymentMethod), validators=[DataRequired()]
    )
    reference = StringField("Reference", validators=[Optional(), Length(max=255)])
    notes = TextAreaField("Notes", validators=[Optional()])
    submit = SubmitField("Record payment")

    def apply(self, payment: Payment) -> Payment:
        payment.amount = decimal_or_zero(self.amount.data)
        payment.method = PaymentMethod(self.method.data)
        payment.reference = self.reference.data or None
        payment.notes = self.notes.data
        return payment
