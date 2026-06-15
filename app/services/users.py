from __future__ import annotations

from sqlalchemy import func, select

from app.extensions import db
from app.models import User, UserRole


def get_user_by_email(email: str) -> User | None:
    statement = select(User).where(func.lower(User.email) == email.strip().lower())
    return db.session.scalar(statement)


def ensure_admin_user(
    email: str,
    password: str,
    first_name: str,
    last_name: str,
) -> tuple[User, bool]:
    return ensure_user(
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        role=UserRole.ADMIN,
    )


def ensure_user(
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    role: UserRole,
) -> tuple[User, bool]:
    existing_user = get_user_by_email(email)
    if existing_user:
        existing_user.first_name = first_name
        existing_user.last_name = last_name
        existing_user.role = role
        existing_user.is_active = True
        db.session.commit()
        return existing_user, False

    user = User(
        email=email.strip().lower(),
        first_name=first_name,
        last_name=last_name,
        role=role,
        is_active=True,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user, True
