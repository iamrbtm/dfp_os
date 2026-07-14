from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.fields.datetime import DateTimeLocalField
from wtforms.validators import DataRequired, Length, Optional

from app.forms.common import enum_choices
from app.models import Collection, CustomRequest, Market, Product
from app.models.promotion import ContentChannel, ContentStatus, SignStatus


class ContentDraftForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=200)])
    content_type = StringField("Content Type", default="social_post", validators=[Optional(), Length(max=60)])
    channel = SelectField("Channel", choices=enum_choices(ContentChannel), validators=[DataRequired()])
    caption = TextAreaField("Caption", validators=[Optional()])
    media_reference = StringField("Media Reference (URL or filename)", validators=[Optional(), Length(max=500)])
    product_id = SelectField("Product", coerce=int, validators=[Optional()])
    market_id = SelectField("Market", coerce=int, validators=[Optional()])
    custom_request_id = SelectField("Custom Request", coerce=int, validators=[Optional()])
    planned_publish_date = DateTimeLocalField("Planned Publish Date", format="%Y-%m-%dT%H:%M", validators=[Optional()])
    status = SelectField("Status", choices=enum_choices(ContentStatus), validators=[DataRequired()])
    notes = TextAreaField("Notes", validators=[Optional()])
    submit = SubmitField("Save Draft")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        products = Product.query.order_by(Product.name).all()
        self.product_id.choices = [(0, "---")] + [(p.id, p.name) for p in products]
        markets = Market.query.order_by(Market.event_date.desc()).all()
        self.market_id.choices = [(0, "---")] + [(m.id, m.name) for m in markets]
        custom_reqs = CustomRequest.query.order_by(CustomRequest.created_at.desc()).limit(50).all()
        self.custom_request_id.choices = [(0, "---")] + [(cr.id, f"#{cr.id}") for cr in custom_reqs]

    def apply(self, draft: ContentDraft) -> ContentDraft:
        draft.title = self.title.data.strip()
        draft.content_type = self.content_type.data.strip() or "social_post"
        draft.channel = ContentChannel(self.channel.data)
        draft.caption = self.caption.data
        draft.media_reference = self.media_reference.data or None
        draft.product_id = self.product_id.data or None
        draft.market_id = self.market_id.data or None
        draft.custom_request_id = self.custom_request_id.data or None
        draft.planned_publish_date = self.planned_publish_date.data
        draft.status = ContentStatus(self.status.data)
        draft.notes = self.notes.data
        return draft


class SignAssetForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=200)])
    subtitle = StringField("Subtitle", validators=[Optional(), Length(max=300)])
    price_display = StringField("Price Display (e.g. $12)", validators=[Optional(), Length(max=60)])
    short_description = TextAreaField("Short Description", validators=[Optional()])
    care_note = TextAreaField("Care Note", validators=[Optional()])
    qr_target_url = StringField("QR Target URL", validators=[Optional(), Length(max=500)])
    layout = SelectField("Layout", choices=[("text", "Text Sign"), ("graphical", "Graphical Sign")], validators=[DataRequired()])
    product_id = SelectField("Product", coerce=int, validators=[Optional()])
    collection_id = SelectField("Collection", coerce=int, validators=[Optional()])
    is_active = BooleanField("Active")
    status = SelectField("Status", choices=enum_choices(SignStatus), validators=[DataRequired()])
    submit = SubmitField("Save Sign")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        products = Product.query.order_by(Product.name).all()
        self.product_id.choices = [(0, "---")] + [(p.id, p.name) for p in products]
        collections = Collection.query.order_by(Collection.name).all()
        self.collection_id.choices = [(0, "---")] + [(c.id, c.name) for c in collections]

    def apply(self, sign: SignAsset) -> SignAsset:
        sign.title = self.title.data.strip()
        sign.subtitle = self.subtitle.data or None
        sign.price_display = self.price_display.data or None
        sign.short_description = self.short_description.data
        sign.care_note = self.care_note.data
        sign.qr_target_url = self.qr_target_url.data or None
        sign.layout = self.layout.data
        sign.product_id = self.product_id.data or None
        sign.collection_id = self.collection_id.data or None
        sign.is_active = bool(self.is_active.data)
        sign.status = SignStatus(self.status.data)
        return sign
