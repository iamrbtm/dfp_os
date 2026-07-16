from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, Optional


class FeatureFlagToggleForm(FlaskForm):
    enabled = BooleanField("Enabled", default=True)
    submit = SubmitField("Toggle")
