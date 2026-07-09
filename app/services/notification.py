from __future__ import annotations

from datetime import datetime, timezone

from app.extensions import db
from app.models.notification import Notification


def create_notification(
    notification_type: str,
    title: str,
    message: str | None = None,
    user_id: int | None = None,
    related_entity_type: str | None = None,
    related_entity_id: str | None = None,
    link: str | None = None,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        notification_type=notification_type,
        title=title,
        message=message,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
        is_read=False,
        link=link,
    )
    db.session.add(notification)
    db.session.commit()
    return notification


def mark_notification_read(notification_id: int) -> Notification | None:
    notification = db.session.get(Notification, notification_id)
    if not notification:
        return None
    notification.is_read = True
    notification.read_at = datetime.now(timezone.utc)
    db.session.commit()
    return notification


def mark_all_read(user_id: int | None = None) -> int:
    query = db.session.query(Notification).filter(Notification.is_read == False)
    if user_id is not None:
        query = query.filter(Notification.user_id == user_id)
    count = query.count()
    now = datetime.now(timezone.utc)
    for notification in query.all():
        notification.is_read = True
        notification.read_at = now
    db.session.commit()
    return count


def get_unread_count(user_id: int | None = None) -> int:
    query = db.session.query(Notification).filter(Notification.is_read == False)
    if user_id is not None:
        query = query.filter(Notification.user_id == user_id)
    return query.count()


def get_notifications(
    user_id: int | None = None,
    limit: int = 50,
    unread_only: bool = False,
) -> list[Notification]:
    query = db.session.query(Notification)
    if user_id is not None:
        query = query.filter(Notification.user_id == user_id)
    if unread_only:
        query = query.filter(Notification.is_read == False)
    return query.order_by(Notification.created_at.desc()).limit(limit).all()
