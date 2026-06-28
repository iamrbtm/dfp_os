from app.extensions import db
from app.models import Business


DEFAULT_BUSINESS_SLUG = "dude-fish-printing"


def get_default_business() -> Business | None:
    return Business.query.filter_by(slug=DEFAULT_BUSINESS_SLUG).first()


def ensure_default_business() -> Business:
    business = get_default_business()
    if business is None:
        business = Business(
            name="Dude Fish Printing",
            slug=DEFAULT_BUSINESS_SLUG,
            legal_name="Dude Fish Printing",
            public_name="Dude Fish Printing",
            contact_email="hello@dudefishprinting.com",
            city="Clarksville",
            state="TN",
            timezone="America/Chicago",
            currency="USD",
            is_active=True,
        )
        db.session.add(business)
        db.session.commit()
    return business
