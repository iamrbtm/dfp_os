from __future__ import annotations

from datetime import datetime, timedelta, timezone


from app.extensions import db
from app.models import (
    CustomRequest,
    CustomRequestStatus,
    FollowUpType,
    Market,
    MarketStatus,
    PosSale,
    PosSaleStatus,
    PosSession,
    PosSessionStatus,
    PrepTask,
    PrepTaskCategory,
    PrepTaskStatus,
)
from app.services.markets import record_market_audit


def generate_market_follow_ups(market: Market, actor=None) -> list[PrepTask]:
    """Generate follow-up tasks from a completed market's POS sales, custom
    requests, and unpaid deposits."""
    generated: list[PrepTask] = []

    if market.status != MarketStatus.COMPLETED:
        return generated

    created = _gen_from_pos_sales(market, generated, actor)
    created += _gen_from_custom_requests(market, generated, actor)
    created += _gen_unpaid_deposits(market, generated, actor)

    for task in created:
        db.session.add(task)
    if created:
        db.session.commit()
        for task in created:
            record_market_audit(
                "prep_task.follow_up_generated",
                "prep_task",
                task.id,
                actor=actor,
                after_state={
                    "market_id": market.id,
                    "title": task.title,
                    "follow_up_type": task.follow_up_type,
                    "customer_id": task.customer_id,
                },
            )
    return created


def _gen_from_pos_sales(market: Market, existing: list[PrepTask], actor=None) -> list[PrepTask]:
    tasks: list[PrepTask] = []
    sessions = PosSession.query.filter(
        PosSession.market_id == market.id,
        PosSession.status != PosSessionStatus.VOIDED,
    ).all()
    session_ids = [s.id for s in sessions]
    if not session_ids:
        return tasks

    sales = PosSale.query.filter(
        PosSale.pos_session_id.in_(session_ids),
        PosSale.status != PosSaleStatus.VOIDED,
    ).all()

    for sale in sales:
        customer_id = None
        if sale.customer_id:
            customer_id = sale.customer_id

        if sale.payment_method and sale.payment_method.lower() not in ("cash", "card"):
            if not _has_follow_up(existing, FollowUpType.UNPAID_DEPOSIT, customer_id, market.id):
                tasks.append(_make_task(
                    market=market,
                    follow_up_type=FollowUpType.UNPAID_DEPOSIT,
                    title=f"Follow up on pending payment: {sale.payment_method} sale for ${float(sale.total):.2f}",
                    customer_id=customer_id,
                    related_pos_sale_id=sale.id,
                    due_days=3,
                ))

        if customer_id:
            if not _has_follow_up(existing, FollowUpType.THANK_YOU, customer_id, market.id):
                tasks.append(_make_task(
                    market=market,
                    follow_up_type=FollowUpType.THANK_YOU,
                    title="Send thank-you to customer from market sale",
                    customer_id=customer_id,
                    related_pos_sale_id=sale.id,
                    due_days=1,
                ))

    return tasks


def _gen_from_custom_requests(market: Market, existing: list[PrepTask], actor=None) -> list[PrepTask]:
    tasks: list[PrepTask] = []
    requests = CustomRequest.query.filter(
        CustomRequest.market_id == market.id,
    ).all()

    for req in requests:
        customer_id = req.customer_id

        if req.status in (CustomRequestStatus.NEW, CustomRequestStatus.NEEDS_REVIEW):
            if not _has_follow_up(existing, FollowUpType.CUSTOM_LEAD, customer_id, market.id):
                tasks.append(_make_task(
                    market=market,
                    follow_up_type=FollowUpType.CUSTOM_LEAD,
                    title=f"Review custom request from {req.customer_name or 'unknown'}",
                    customer_id=customer_id,
                    related_custom_request_id=req.id,
                    due_days=2,
                ))

        elif req.status == CustomRequestStatus.QUOTE_SENT:
            if not _has_follow_up(existing, FollowUpType.QUOTE_FOLLOW_UP, customer_id, market.id):
                tasks.append(_make_task(
                    market=market,
                    follow_up_type=FollowUpType.QUOTE_FOLLOW_UP,
                    title=f"Follow up on quote sent to {req.customer_name or 'unknown'}",
                    customer_id=customer_id,
                    related_custom_request_id=req.id,
                    due_days=5,
                ))

    return tasks


def _gen_unpaid_deposits(market: Market, existing: list[PrepTask], actor=None) -> list[PrepTask]:
    tasks: list[PrepTask] = []
    session_ids = [s.id for s in PosSession.query.filter(
        PosSession.market_id == market.id,
        PosSession.status != PosSessionStatus.VOIDED,
    ).all()]
    if not session_ids:
        return tasks

    deposits = PosSale.query.filter(
        PosSale.pos_session_id.in_(session_ids),
        PosSale.status == PosSaleStatus.PENDING,
    ).all()

    for deposit in deposits:
        customer_id = deposit.customer_id
        if not _has_follow_up(existing, FollowUpType.UNPAID_DEPOSIT, customer_id, market.id):
            tasks.append(_make_task(
                market=market,
                follow_up_type=FollowUpType.UNPAID_DEPOSIT,
                title=f"Collect unpaid deposit from market ({deposit.description or 'sale'} - ${float(deposit.total):.2f})",
                customer_id=customer_id,
                related_pos_sale_id=deposit.id,
                due_days=3,
            ))

    return tasks


def _make_task(
    *,
    market: Market,
    follow_up_type: FollowUpType,
    title: str,
    customer_id: int | None = None,
    related_pos_sale_id: int | None = None,
    related_custom_request_id: int | None = None,
    related_order_id: int | None = None,
    due_days: int = 3,
) -> PrepTask:
    return PrepTask(
        market_id=market.id,
        title=title,
        category=PrepTaskCategory.FOLLOW_UP,
        status=PrepTaskStatus.OPEN,
        follow_up_type=follow_up_type.value,
        customer_id=customer_id,
        related_pos_sale_id=related_pos_sale_id,
        related_custom_request_id=related_custom_request_id,
        related_order_id=related_order_id,
        source="market_follow_up",
        due_at=datetime.now(timezone.utc) + timedelta(days=due_days),
    )


def _has_follow_up(
    existing: list[PrepTask],
    follow_up_type: FollowUpType,
    customer_id: int | None,
    market_id: int,
) -> bool:
    return any(
        t.follow_up_type == follow_up_type.value
        and t.customer_id == customer_id
        and t.market_id == market_id
        and t.status != PrepTaskStatus.CANCELED
        for t in existing
    )


def complete_follow_up(task: PrepTask, actor=None) -> PrepTask:
    from app.models.base import utc_now

    task.status = PrepTaskStatus.COMPLETED
    task.completed_at = utc_now()
    db.session.commit()
    record_market_audit(
        "prep_task.follow_up_completed",
        "prep_task",
        task.id,
        actor=actor,
        after_state={
            "title": task.title,
            "follow_up_type": task.follow_up_type,
            "market_id": task.market_id,
        },
    )
    return task


def reopen_follow_up(task: PrepTask, actor=None) -> PrepTask:
    task.status = PrepTaskStatus.REOPENED
    task.completed_at = None
    db.session.commit()
    record_market_audit(
        "prep_task.follow_up_reopened",
        "prep_task",
        task.id,
        actor=actor,
        after_state={
            "title": task.title,
            "follow_up_type": task.follow_up_type,
            "market_id": task.market_id,
        },
    )
    return task


def archive_follow_up(task: PrepTask, actor=None) -> PrepTask:
    task.status = PrepTaskStatus.CANCELED
    db.session.commit()
    record_market_audit(
        "prep_task.follow_up_archived",
        "prep_task",
        task.id,
        actor=actor,
        after_state={
            "title": task.title,
            "follow_up_type": task.follow_up_type,
            "market_id": task.market_id,
        },
    )
    return task


def get_follow_up_queue(market_id: int | None = None) -> list[PrepTask]:
    query = PrepTask.query.filter(
        PrepTask.category == PrepTaskCategory.FOLLOW_UP,
        PrepTask.status.in_([PrepTaskStatus.OPEN, PrepTaskStatus.IN_PROGRESS, PrepTaskStatus.REOPENED]),
    )
    if market_id:
        query = query.filter(PrepTask.market_id == market_id)
    return query.order_by(
        PrepTask.due_at.is_(None).asc(),
        PrepTask.due_at.asc(),
        PrepTask.created_at.desc(),
    ).all()
