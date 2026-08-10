from __future__ import annotations


from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DateField,
    DecimalField,
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.fields.datetime import TimeField
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional, URL

from app.forms.common import enum_choices
from app.models import (
    MarketCatalogBoothTier,
    MarketCatalogListing,
    MarketCategory,
    MarketInterestLevel,
    MarketStatus,
)


def _category_choices():
    categories = (
        MarketCategory.query.filter(MarketCategory.deleted_at.is_(None))
        .order_by(MarketCategory.sort_order.asc(), MarketCategory.name.asc())
        .all()
    )
    return [("", "---")] + [(c.id, c.name) for c in categories]


def _interest_choices():
    return enum_choices(MarketInterestLevel)


class MarketCategoryForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=80)])
    description = TextAreaField("Description", validators=[Optional()])
    sort_order = IntegerField("Sort Order", validators=[Optional(), NumberRange(min=0)], default=0)
    is_active = BooleanField("Active", default=True)
    submit = SubmitField("Save category")

    def apply(self, category: MarketCategory) -> MarketCategory:
        category.name = self.name.data.strip()
        category.description = self.description.data or None
        category.sort_order = self.sort_order.data or 0
        category.is_active = bool(self.is_active.data)
        return category


class MarketCatalogBoothTierForm(FlaskForm):
    label = StringField("Label", validators=[Optional(), Length(max=80)])
    dimensions = StringField("Dimensions", validators=[Optional(), Length(max=80)])
    price = DecimalField("Price", places=2, validators=[Optional()])
    corner_premium = DecimalField("Corner Premium", places=2, validators=[Optional()])
    notes = StringField("Notes", validators=[Optional(), Length(max=200)])
    sort_order = IntegerField("Sort", validators=[Optional(), NumberRange(min=0)], default=0)

    def apply(self, tier: MarketCatalogBoothTier) -> MarketCatalogBoothTier:
        tier.label = (self.label.data or "").strip() or "Booth"
        tier.dimensions = self.dimensions.data or None
        tier.price = self.price.data
        tier.corner_premium = self.corner_premium.data
        tier.notes = self.notes.data or None
        tier.sort_order = self.sort_order.data or 0
        return tier


class MarketCatalogListingForm(FlaskForm):
    # Identity
    name = StringField("Name", validators=[DataRequired(), Length(max=200)])
    category_id = SelectField(
        "Category", coerce=lambda x: int(x) if x else None, validators=[Optional()]
    )
    description = TextAreaField("Description", validators=[Optional()])
    website_url = StringField("Website", validators=[Optional(), Length(max=500), URL()])

    # Location
    location_name = StringField("Location Name", validators=[Optional(), Length(max=200)])
    address = StringField("Address", validators=[Optional(), Length(max=300)])
    city = StringField("City", validators=[Optional(), Length(max=100)])
    state = StringField("State", validators=[Optional(), Length(max=50)])
    zip_code = StringField("ZIP", validators=[Optional(), Length(max=20)])
    latitude = DecimalField("Latitude", places=6, validators=[Optional()])
    longitude = DecimalField("Longitude", places=6, validators=[Optional()])

    # Timing
    default_start_time = TimeField("Default Start", format="%H:%M", validators=[Optional()])
    default_end_time = TimeField("Default End", format="%H:%M", validators=[Optional()])
    timezone = StringField("Timezone", validators=[Optional(), Length(max=50)])

    # Recurrence
    is_recurring = BooleanField("Recurring")
    rrule = TextAreaField("RRULE", validators=[Optional()])
    recurrence_description = StringField(
        "Recurrence Description", validators=[Optional(), Length(max=255)]
    )

    # Scale
    estimated_vendor_count = IntegerField(
        "Est. Vendors", validators=[Optional(), NumberRange(min=0)]
    )
    estimated_attendee_count = IntegerField(
        "Est. Attendees", validators=[Optional(), NumberRange(min=0)]
    )

    # Amenities
    power_available = BooleanField("Power")
    wifi_available = BooleanField("Wi-Fi")
    food_available = BooleanField("Food")
    restrooms_available = BooleanField("Restrooms")
    indoor = BooleanField("Indoor")
    covered_outdoor = BooleanField("Covered Outdoor")
    outdoor = BooleanField("Outdoor")
    parking_notes = TextAreaField("Parking Notes", validators=[Optional()])

    # Organizer
    organizer_name = StringField("Organizer", validators=[Optional(), Length(max=200)])
    organizer_email = StringField("Email", validators=[Optional(), Length(max=200), Email()])
    organizer_phone = StringField("Phone", validators=[Optional(), Length(max=60)])
    application_url = StringField(
        "Application URL", validators=[Optional(), Length(max=500), URL()]
    )
    application_contact = StringField(
        "Application Contact", validators=[Optional(), Length(max=200)]
    )
    application_deadline_description = StringField(
        "Deadline Notes", validators=[Optional(), Length(max=255)]
    )

    # Rules
    booth_rules = TextAreaField("Booth Rules", validators=[Optional()])
    required_documents = TextAreaField("Required Documents", validators=[Optional()])
    notes = TextAreaField("Notes", validators=[Optional()])

    # Tracking
    interest_level = SelectField(
        "Interest Level", choices=_interest_choices(), validators=[DataRequired()]
    )

    submit = SubmitField("Save listing")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.category_id.choices = _category_choices()

    def apply(self, listing: MarketCatalogListing) -> MarketCatalogListing:
        listing.name = self.name.data.strip()
        listing.category_id = self.category_id.data or None
        listing.description = self.description.data or None
        listing.website_url = self.website_url.data or None
        listing.location_name = self.location_name.data or None
        listing.address = self.address.data or None
        listing.city = self.city.data or None
        listing.state = self.state.data or None
        listing.zip_code = self.zip_code.data or None
        listing.latitude = float(self.latitude.data) if self.latitude.data is not None else None
        listing.longitude = float(self.longitude.data) if self.longitude.data is not None else None
        listing.default_start_time = self.default_start_time.data
        listing.default_end_time = self.default_end_time.data
        listing.timezone = self.timezone.data or "America/Chicago"
        listing.is_recurring = bool(self.is_recurring.data)
        listing.rrule = self.rrule.data or None
        listing.recurrence_description = self.recurrence_description.data or None
        listing.estimated_vendor_count = self.estimated_vendor_count.data
        listing.estimated_attendee_count = self.estimated_attendee_count.data
        listing.power_available = bool(self.power_available.data)
        listing.wifi_available = bool(self.wifi_available.data)
        listing.food_available = bool(self.food_available.data)
        listing.restrooms_available = bool(self.restrooms_available.data)
        listing.indoor = bool(self.indoor.data)
        listing.covered_outdoor = bool(self.covered_outdoor.data)
        listing.outdoor = bool(self.outdoor.data)
        listing.parking_notes = self.parking_notes.data or None
        listing.organizer_name = self.organizer_name.data or None
        listing.organizer_email = self.organizer_email.data or None
        listing.organizer_phone = self.organizer_phone.data or None
        listing.application_url = self.application_url.data or None
        listing.application_contact = self.application_contact.data or None
        listing.application_deadline_description = (
            self.application_deadline_description.data or None
        )
        listing.booth_rules = self.booth_rules.data or None
        listing.required_documents = self.required_documents.data or None
        listing.notes = self.notes.data or None
        listing.interest_level = MarketInterestLevel(self.interest_level.data)
        return listing


class BookFromCatalogForm(FlaskForm):
    event_date = DateField("Event Date", format="%Y-%m-%d", validators=[DataRequired()])
    booth_tier_id = SelectField(
        "Booth Tier", coerce=lambda x: int(x) if x else None, validators=[Optional()]
    )
    apply_corner_premium = BooleanField("Apply corner premium")
    status = SelectField(
        "Status",
        choices=[
            (MarketStatus.INTERESTED.value, "Interested"),
            (MarketStatus.APPLIED.value, "Applied"),
        ],
        default=MarketStatus.INTERESTED.value,
        validators=[DataRequired()],
    )
    submit = SubmitField("Book this market")

    def __init__(self, listing=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if listing is not None:
            self.booth_tier_id.choices = [("", "First available")] + [
                (t.id, t.display_price) for t in listing.booth_tiers
            ]
