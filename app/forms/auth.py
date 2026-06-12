from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, Length


class LoginForm(FlaskForm):
    email = StringField(
        "Email",
        validators=[DataRequired(), Email(), Length(max=255)],
        render_kw={"autocomplete": "email", "placeholder": "admin@example.com"},
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(min=8, max=255)],
        render_kw={"autocomplete": "current-password", "placeholder": "••••••••"},
    )
    remember_me = BooleanField("Keep me signed in")
    submit = SubmitField("Sign in")
