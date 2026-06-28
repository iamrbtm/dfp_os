from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import HiddenField, IntegerField, RadioField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional


class AddToCartForm(FlaskForm):
    product_id = HiddenField(validators=[DataRequired()])
    quantity = IntegerField("Quantity", validators=[DataRequired(), NumberRange(min=1, max=25)], default=1)
    submit = SubmitField("Add to cart")


class CheckoutForm(FlaskForm):
    first_name = StringField("First name", validators=[DataRequired(), Length(max=120)])
    last_name = StringField("Last name", validators=[DataRequired(), Length(max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    phone = StringField("Phone", validators=[Optional(), Length(max=50)])
    fulfillment_method = RadioField(
        "How would you like to receive your order?",
        choices=[("pickup", "Local pickup"), ("shipping", "Ship to me")],
        default="pickup",
        validators=[DataRequired()],
    )
    shipping_name = StringField("Recipient name", validators=[Optional(), Length(max=255)])
    shipping_address_line_1 = StringField("Street address", validators=[Optional(), Length(max=255)])
    shipping_address_line_2 = StringField("Apartment, suite, etc. (optional)", validators=[Optional(), Length(max=255)])
    shipping_city = StringField("City", validators=[Optional(), Length(max=120)])
    shipping_state = StringField("State", validators=[Optional(), Length(max=120)])
    shipping_postal_code = StringField("ZIP code", validators=[Optional(), Length(max=20)])
    payment_option = RadioField(
        "Payment option",
        choices=[("square", "Pay online with Square"), ("venmo", "Reserve now, pay by Venmo")],
        default="square",
        validators=[DataRequired()],
    )
    notes = TextAreaField("Order notes (optional)", validators=[Optional(), Length(max=4000)])
    submit = SubmitField("Continue to payment")

    def validate(self, extra_validators=None):
        is_valid = super().validate(extra_validators=extra_validators)
        if not is_valid:
            return False

        if self.fulfillment_method.data == "shipping":
            required_fields = [
                self.shipping_name,
                self.shipping_address_line_1,
                self.shipping_city,
                self.shipping_state,
                self.shipping_postal_code,
            ]
            missing = False
            for field in required_fields:
                if not (field.data or "").strip():
                    field.errors.append("This field is required for shipped orders.")
                    missing = True
            if missing:
                return False

        return True
