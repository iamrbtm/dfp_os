from __future__ import annotations

from enum import Enum

from sqlalchemy import or_

from app.extensions import db
from app.models.base import utc_now


def apply_search(statement, model, search_term: str | None, field_names: list[str]):
    if not search_term or not field_names:
        return statement

    term = f"%{search_term.strip()}%"
    clauses = [getattr(model, field_name).ilike(term) for field_name in field_names]
    return statement.where(or_(*clauses))


def paginate_query(statement, page: int, per_page: int):
    return db.paginate(statement, page=page, per_page=per_page, error_out=False)


def save_instance(instance):
    db.session.add(instance)
    db.session.commit()
    return instance


def archive_instance(instance):
    if hasattr(instance, "deleted_at"):
        instance.deleted_at = utc_now()
    elif hasattr(instance, "active"):
        instance.active = False
    elif hasattr(instance, "is_public"):
        instance.is_public = False
    elif hasattr(instance, "is_active"):
        instance.is_active = False
    elif hasattr(instance, "status"):
        current_status = getattr(instance, "status")
        enum_class = type(current_status)
        if issubclass(enum_class, Enum):
            for fallback in ("RETIRED", "ARCHIVED", "HIDDEN"):
                if hasattr(enum_class, fallback):
                    instance.status = getattr(enum_class, fallback)
                    break
    db.session.commit()
    return instance


def get_by_id(model, resource_id: int):
    return db.session.get(model, resource_id)
