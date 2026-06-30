from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.extensions import db
from app.models.order import (
    Order,
    OrderItem,
    OrderPaymentStatus,
    OrderSource,
    OrderStatus,
    Payment,
    PaymentMethod,
)
from app.models.demand import InternalDemandEventType
from app.models.pos import (
    PosSale,
    PosSaleItem,
    PosSaleItemType,
    PosSaleStatus,
    PosSession,
    PosSessionStatus,
)
from app.services.audit import record_audit_event
from app.services.internal_demand import record_demand_event
from app.services.inventory import deduct_finished_goods, return_inventory


def open_session(
    user_id: int,
    opening_cash: Decimal,
    market_id: int | None = None,
    inventory_location_id: int | None = None,
    notes: str | None = None,
) -> PosSession:
    session = PosSession(
        opened_by_user_id=user_id,
        opening_cash=opening_cash,
        market_id=market_id,
        inventory_location_id=inventory_location_id,
        notes=notes,
    )
    db.session.add(session)
    db.session.commit()
    record_audit_event(
        action="pos_session.opened",
        entity_type="pos_session",
        entity_id=session.id,
        after_state={
            "opening_cash": str(session.opening_cash),
            "market_id": session.market_id,
            "inventory_location_id": session.inventory_location_id,
        },
        source_module=__name__,
        actor_id=user_id,
    )
    return session


def close_session(
    session_id: int,
    closed_by_user_id: int,
    closing_cash: Decimal,
    notes: str | None = None,
) -> PosSession:
    session = db.session.get(PosSession, session_id)
    if not session or session.status != PosSessionStatus.OPEN:
        raise ValueError("Session is not open")

    summary = get_session_summary(session_id)

    session.closing_cash = closing_cash
    session.expected_cash = summary["expected_cash"]
    session.cash_difference = closing_cash - session.expected_cash
    session.closed_by_user_id = closed_by_user_id
    session.closed_at = datetime.now(timezone.utc)
    session.status = PosSessionStatus.CLOSED
    if notes:
        session.notes = (session.notes or "") + f"\nClose notes: {notes}"
    db.session.commit()
    record_audit_event(
        action="pos_session.closed",
        entity_type="pos_session",
        entity_id=session.id,
        after_state={
            "closing_cash": str(session.closing_cash),
            "expected_cash": str(session.expected_cash),
            "cash_difference": str(session.cash_difference),
            "cash_sales_total": str(summary["cash_sales_total"]),
            "cash_refunds_total": str(summary["cash_refunds_total"]),
        },
        source_module=__name__,
        actor_id=closed_by_user_id,
    )
    return session


def void_session(session_id: int) -> PosSession:
    session = db.session.get(PosSession, session_id)
    if not session:
        raise ValueError("Session not found")
    session.status = PosSessionStatus.VOIDED
    db.session.commit()
    record_audit_event(
        action="pos_session.voided",
        entity_type="pos_session",
        entity_id=session.id,
        source_module=__name__,
    )
    return session


def create_sale(
    session_id: int,
    payment_method: str,
    amount_received: Decimal,
    items: list[dict],
    customer_id: int | None = None,
    notes: str | None = None,
    tax_total: Decimal | None = None,
) -> tuple[PosSale, Order]:
    session = db.session.get(PosSession, session_id)
    if not session or session.status != PosSessionStatus.OPEN:
        raise ValueError("Session is not open")

    subtotal = Decimal("0")
    discount_total = Decimal("0")
    pos_items = []

    for item_data in items:
        qty = Decimal(str(item_data["quantity"]))
        unit_price = Decimal(str(item_data["unit_price"]))
        discount = Decimal(str(item_data.get("discount_amount", 0)))
        line_total = qty * unit_price - discount
        subtotal += qty * unit_price
        discount_total += discount

        pos_item = PosSaleItem(
            product_id=item_data.get("product_id"),
            quantity=item_data["quantity"],
            unit_price=unit_price,
            discount_amount=discount,
            line_total=line_total,
            item_type=item_data.get("item_type", PosSaleItemType.PRODUCT.value),
            description=item_data.get("description", ""),
            custom_notes=item_data.get("custom_notes"),
        )
        pos_items.append(pos_item)

    if tax_total is None:
        tax_total = Decimal("0")
    total = subtotal - discount_total + tax_total
    change_due = max(Decimal("0"), Decimal(str(amount_received)) - total)

    order = Order(
        source=OrderSource.POS,
        status=OrderStatus.COMPLETED,
        market_id=session.market_id,
        pos_session_id=session.id,
        customer_id=customer_id,
        subtotal=subtotal,
        discount_total=discount_total,
        tax_total=tax_total,
        total=total,
        paid_amount=total,
        completed_at=datetime.now(timezone.utc),
    )
    db.session.add(order)
    db.session.flush()

    for item_data, pos_item in zip(items, pos_items):
        order_item = OrderItem(
            order_id=order.id,
            product_id=item_data.get("product_id"),
            quantity=item_data["quantity"],
            unit_price=Decimal(str(item_data["unit_price"])),
            line_total=pos_item.line_total,
            is_custom_item=item_data.get("item_type", "product") != "product",
            custom_description=(
                item_data.get("description") if item_data.get("item_type") != "product" else None
            ),
        )
        db.session.add(order_item)

    payment = Payment(
        order_id=order.id,
        amount=total,
        method=PaymentMethod(payment_method),
        notes=notes,
        payment_date=datetime.now(timezone.utc),
    )
    db.session.add(payment)

    sale = PosSale(
        pos_session_id=session_id,
        order_id=order.id,
        customer_id=customer_id,
        subtotal=subtotal,
        discount_total=discount_total,
        tax_total=tax_total,
        total=total,
        payment_method=payment_method,
        amount_received=Decimal(str(amount_received)),
        change_due=change_due,
        status=PosSaleStatus.COMPLETED,
        notes=notes,
        items=pos_items,
    )
    db.session.add(sale)

    db.session.flush()
    _deduct_inventory_for_sale(sale, session.inventory_location_id, session.opened_by_user_id)

    db.session.commit()
    for item in sale.items:
        if item.item_type != PosSaleItemType.PRODUCT or item.product_id is None:
            continue
        record_demand_event(
            InternalDemandEventType.POS_SALE_COMPLETED,
            source="pos",
            product_id=item.product_id,
            order_id=order.id,
            quantity=item.quantity,
            value=item.line_total,
            metadata={
                "pos_sale_id": sale.id,
                "pos_session_id": session.id,
                "market_id": session.market_id,
                "payment_method": payment_method,
            },
        )
    record_audit_event(
        action="pos_sale.completed",
        entity_type="pos_sale",
        entity_id=sale.id,
        after_state={
            "sale_number": sale.sale_number,
            "order_id": order.id,
            "total": str(sale.total),
            "payment_method": sale.payment_method,
            "market_id": session.market_id,
            "inventory_location_id": session.inventory_location_id,
        },
        source_module=__name__,
        actor_id=session.opened_by_user_id,
    )

    return sale, order


def _deduct_inventory_for_sale(
    sale: PosSale,
    inventory_location_id: int | None,
    actor_id: int | None,
) -> None:
    for item in sale.items:
        if item.item_type != PosSaleItemType.PRODUCT or item.product_id is None:
            continue
        deduct_finished_goods(
            product_id=item.product_id,
            quantity=item.quantity,
            location_id=inventory_location_id,
            reference_type="pos_sale",
            reference_id=sale.id,
            actor_id=actor_id,
        )


def get_session_summary(session_id: int) -> dict:
    session = db.session.get(PosSession, session_id)
    if not session:
        raise ValueError("Session not found")

    sales = PosSale.query.filter_by(pos_session_id=session_id, status=PosSaleStatus.COMPLETED).all()
    refunded_sales = PosSale.query.filter_by(
        pos_session_id=session_id,
        status=PosSaleStatus.REFUNDED,
    ).all()
    total_sales = sum(s.total for s in sales)
    refunded_total = sum(s.total for s in refunded_sales)
    payment_totals: dict[str, Decimal] = {}
    for s in sales:
        pm = str(s.payment_method)
        payment_totals[pm] = payment_totals.get(pm, Decimal("0")) + s.total

    cash_sales_total = sum(s.total for s in sales if s.payment_method == PaymentMethod.CASH.value)
    cash_refunds_total = sum(
        s.total for s in refunded_sales if s.payment_method == PaymentMethod.CASH.value
    )
    expected_cash = (
        session.opening_cash + Decimal(str(cash_sales_total)) - Decimal(str(cash_refunds_total))
    )

    return {
        "session": session,
        "sales": sales,
        "refunded_sales": refunded_sales,
        "total_sales": total_sales,
        "refunded_total": refunded_total,
        "net_sales_total": total_sales - refunded_total,
        "sale_count": len(sales),
        "refund_count": len(refunded_sales),
        "payment_totals": payment_totals,
        "cash_sales_total": cash_sales_total,
        "cash_refunds_total": cash_refunds_total,
        "expected_cash": expected_cash,
    }


def refund_sale(
    *,
    sale_id: int,
    actor_id: int | None = None,
    restock: bool = True,
    notes: str | None = None,
) -> PosSale:
    sale = db.session.get(PosSale, sale_id)
    if sale is None:
        raise ValueError("Sale not found")
    if sale.status != PosSaleStatus.COMPLETED:
        raise ValueError("Only completed sales can be refunded")

    session = sale.session
    if session is None:
        raise ValueError("Sale session not found")

    before = {"status": sale.status.value, "total": str(sale.total)}
    sale.status = PosSaleStatus.REFUNDED
    if notes:
        sale.notes = f"{sale.notes}\nRefund: {notes}".strip() if sale.notes else f"Refund: {notes}"

    if sale.order:
        sale.order.status = OrderStatus.REFUNDED
        sale.order.payment_status = OrderPaymentStatus.REFUNDED
        sale.order.paid_amount = Decimal("0.00")
        refund_payment = Payment(
            order_id=sale.order.id,
            amount=Decimal("0.00") - sale.total,
            method=PaymentMethod(sale.payment_method),
            notes=notes or f"Refund for POS sale {sale.sale_number}",
            payment_date=datetime.now(timezone.utc),
        )
        db.session.add(refund_payment)

    if restock:
        for item in sale.items:
            if item.item_type != PosSaleItemType.PRODUCT or item.product_id is None:
                continue
            return_inventory(
                product_id=item.product_id,
                quantity=item.quantity,
                location_id=session.inventory_location_id,
                reference_type="pos_refund",
                reference_id=sale.id,
                actor_id=actor_id,
                notes=notes or f"Refund for {sale.sale_number}",
            )

    db.session.commit()
    record_audit_event(
        action="pos_sale.refunded",
        entity_type="pos_sale",
        entity_id=sale.id,
        before_state=before,
        after_state={"status": sale.status.value, "restocked": restock},
        metadata={"notes": notes, "session_id": session.id},
        source_module=__name__,
        actor_id=actor_id,
    )
    return sale
