from __future__ import annotations

from sqlalchemy import func, select

from app.extensions import db
from app.models import User
from app.models.base import utc_now


def authenticate_user(email: str, password: str) -> User | None:
    normalized_email = email.strip().lower()
    statement = select(User).where(func.lower(User.email) == normalized_email)
    user = db.session.scalar(statement)

    if user is None or not user.is_active or not user.check_password(password):
        return None

    user.last_login_at = utc_now()
    db.session.commit()
    return user
