from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Optional

from app.models import Customer


class CustomerForm(FlaskForm):
    first_name = StringField("First Name", validators=[DataRequired(), Length(max=120)])
    last_name = StringField("Last Name", validators=[DataRequired(), Length(max=120)])
    email = StringField("Email", validators=[Optional(), Length(max=255)])
    phone = StringField("Phone", validators=[Optional(), Length(max=50)])
    address_line_1 = StringField("Address Line 1", validators=[Optional(), Length(max=255)])
    address_line_2 = StringField("Address Line 2", validators=[Optional(), Length(max=255)])
    city = StringField("City", validators=[Optional(), Length(max=120)])
    state = StringField("State", validators=[Optional(), Length(max=120)])
    zip_code = StringField("Zip Code", validators=[Optional(), Length(max=20)])
    notes = TextAreaField("Notes", validators=[Optional()])
    is_active = BooleanField("Active", default=True)
    submit = SubmitField("Save customer")

    def apply(self, customer: Customer) -> Customer:
        customer.first_name = self.first_name.data.strip()
        customer.last_name = self.last_name.data.strip()
        customer.email = self.email.data.strip() if self.email.data else None
        customer.phone = self.phone.data.strip() if self.phone.data else None
        customer.address_line_1 = self.address_line_1.data.strip() if self.address_line_1.data else None
        customer.address_line_2 = self.address_line_2.data.strip() if self.address_line_2.data else None
        customer.city = self.city.data.strip() if self.city.data else None
        customer.state = self.state.data.strip() if self.state.data else None
        customer.zip_code = self.zip_code.data.strip() if self.zip_code.data else None
        customer.notes = self.notes.data
        customer.is_active = bool(self.is_active.data)
        return customer
