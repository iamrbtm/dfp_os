from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.fields.datetime import DateTimeLocalField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, URL, ValidationError

from app.forms.common import enum_choices
from app.models import Business, FeatureFlag, PrepTask, PrepTaskCategory, PrepTaskStatus, PrepTaskTemplate, User
from app.utils import slugify


class BusinessForm(FlaskForm):
    name = StringField("Business Name", validators=[DataRequired(), Length(max=160)])
    slug = StringField("Slug", validators=[Optional(), Length(max=180)])
    legal_name = StringField("Legal Name", validators=[Optional(), Length(max=200)])
    public_name = StringField("Public Name", validators=[Optional(), Length(max=200)])
    contact_email = StringField("Contact Email", validators=[Optional(), Length(max=255)])
    phone = StringField("Phone", validators=[Optional(), Length(max=80)])
    website_url = StringField("Website URL", validators=[Optional(), URL(), Length(max=255)])
    address_line1 = StringField("Address Line 1", validators=[Optional(), Length(max=255)])
    address_line2 = StringField("Address Line 2", validators=[Optional(), Length(max=255)])
    city = StringField("City", validators=[Optional(), Length(max=120)])
    state = StringField("State", validators=[Optional(), Length(max=80)])
    postal_code = StringField("Postal Code", validators=[Optional(), Length(max=40)])
    timezone = StringField("Timezone", validators=[DataRequired(), Length(max=80)])
    currency = StringField("Currency", validators=[DataRequired(), Length(max=3)])
    is_active = BooleanField("Active", default=True)
    submit = SubmitField("Save business")

    def validate_slug(self, field):
        raw = (field.data or "").strip()
        if not raw:
            raw = slugify((self.name.data or "").strip())
            field.data = raw
        if not raw:
            return
        existing = Business.query.filter_by(slug=raw).first()
        if existing and getattr(self, "instance_id", None) != existing.id:
            raise ValidationError("A business with that slug already exists.")

    def apply(self, business: Business) -> Business:
        business.name = self.name.data.strip()
        business.slug = slugify(self.slug.data or "") or slugify(self.name.data.strip())
        business.legal_name = self.legal_name.data or None
        business.public_name = self.public_name.data or None
        business.contact_email = self.contact_email.data or None
        business.phone = self.phone.data or None
        business.website_url = self.website_url.data or None
        business.address_line1 = self.address_line1.data or None
        business.address_line2 = self.address_line2.data or None
        business.city = self.city.data or None
        business.state = self.state.data or None
        business.postal_code = self.postal_code.data or None
        business.timezone = self.timezone.data.strip()
        business.currency = self.currency.data.strip().upper()
        business.is_active = bool(self.is_active.data)
        return business


class FeatureFlagForm(FlaskForm):
    key = StringField("Flag Key", validators=[DataRequired(), Length(max=120)])
    enabled = BooleanField("Enabled", default=True)
    description = StringField("Description", validators=[Optional(), Length(max=255)])
    business_id = SelectField("Business", coerce=int, validators=[Optional()], default=0)
    submit = SubmitField("Save flag")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.business_id.choices = [(0, "Global")] + [
            (business.id, business.name) for business in Business.query.order_by(Business.name)
        ]

    def validate_key(self, field):
        existing = FeatureFlag.query.filter_by(key=field.data.strip(), business_id=self.business_id.data or None).first()
        if existing and getattr(self, "instance_id", None) != existing.id:
            raise ValidationError("A feature flag with that key already exists for this scope.")

    def apply(self, flag: FeatureFlag) -> FeatureFlag:
        flag.key = self.key.data.strip()
        flag.enabled = bool(self.enabled.data)
        flag.description = self.description.data or None
        flag.business_id = self.business_id.data or None
        return flag


class PrepTaskTemplateForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=200)])
    category = SelectField("Category", choices=enum_choices(PrepTaskCategory), validators=[DataRequired()])
    description = TextAreaField("Description", validators=[Optional()])
    default_due_days_before = IntegerField("Days Before Event", validators=[DataRequired(), NumberRange(min=0)], default=7)
    default_enabled = BooleanField("Enabled By Default", default=True)
    submit = SubmitField("Save template")

    def apply(self, template: PrepTaskTemplate) -> PrepTaskTemplate:
        template.title = self.title.data.strip()
        template.category = PrepTaskCategory(self.category.data)
        template.description = self.description.data
        template.default_due_days_before = self.default_due_days_before.data or 0
        template.default_enabled = bool(self.default_enabled.data)
        return template


class PrepTaskAdminForm(FlaskForm):
    market_id = SelectField("Market", coerce=int, validators=[Optional()], default=0)
    template_id = SelectField("Template", coerce=int, validators=[Optional()], default=0)
    title = StringField("Title", validators=[DataRequired(), Length(max=200)])
    category = SelectField("Category", choices=enum_choices(PrepTaskCategory), validators=[DataRequired()])
    status = SelectField("Status", choices=enum_choices(PrepTaskStatus), validators=[DataRequired()])
    assigned_user_id = SelectField("Assigned User", coerce=int, validators=[Optional()], default=0)
    due_at = DateTimeLocalField("Due At", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    source = StringField("Source", validators=[DataRequired(), Length(max=80)], default="manual")
    notes = TextAreaField("Notes", validators=[Optional()])
    submit = SubmitField("Save prep task")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from app.models import Market

        self.market_id.choices = [(0, "No market")] + [(item.id, item.name) for item in Market.query.order_by(Market.event_date.desc(), Market.name)]
        self.template_id.choices = [(0, "No template")] + [(item.id, item.title) for item in PrepTaskTemplate.query.order_by(PrepTaskTemplate.title)]
        self.assigned_user_id.choices = [(0, "Unassigned")] + [(item.id, item.full_name) for item in User.query.order_by(User.first_name, User.last_name)]

    def apply(self, task: PrepTask) -> PrepTask:
        task.market_id = self.market_id.data or None
        task.template_id = self.template_id.data or None
        task.title = self.title.data.strip()
        task.category = PrepTaskCategory(self.category.data)
        task.status = PrepTaskStatus(self.status.data)
        task.assigned_user_id = self.assigned_user_id.data or None
        task.due_at = self.due_at.data
        task.source = self.source.data.strip()
        task.notes = self.notes.data
        return task
