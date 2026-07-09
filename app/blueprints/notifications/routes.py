from __future__ import annotations

from flask import jsonify, render_template, request

from app.blueprints.notifications import bp
from app.models import UserRole
from app.services.notification import (
    get_notifications,
    get_unread_count,
    mark_all_read,
    mark_notification_read,
)
from app.utils.auth import roles_required


@bp.get("/")
@roles_required(UserRole.ADMIN)
def notification_list():
    user_id = request.args.get("user_id", type=int)
    unread_only = request.args.get("unread_only", type=bool, default=False)
    notifications = get_notifications(user_id=user_id, unread_only=unread_only)
    unread_count = get_unread_count(user_id=user_id)
    return render_template(
        "notifications/index.html",
        notifications=notifications,
        unread_count=unread_count,
    )


@bp.get("/unread-count")
@roles_required(UserRole.ADMIN)
def unread_count():
    user_id = request.args.get("user_id", type=int)
    count = get_unread_count(user_id=user_id)
    return jsonify({"count": count})


@bp.post("/<int:notification_id>/read")
@roles_required(UserRole.ADMIN)
def mark_read(notification_id: int):
    notification = mark_notification_read(notification_id)
    if not notification:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"status": "read"})


@bp.post("/mark-all-read")
@roles_required(UserRole.ADMIN)
def mark_all_read_route():
    user_id = request.args.get("user_id", type=int)
    count = mark_all_read(user_id=user_id)
    return jsonify({"status": "ok", "marked_read": count})
