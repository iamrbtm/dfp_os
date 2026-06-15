from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.extensions import db
from app.models.inventory import InventoryRecord
from app.models.order import Order, OrderItem, OrderSource, OrderStatus, Payment, PaymentMethod
from app.models.pos import (
    PosSale,
    PosSaleItem,
    PosSaleItemType,
    PosSaleStatus,
    PosSession,
    PosSessionStatus,
)


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

    total_cash_sales = (
        db.session.query(db.func.coalesce(db.func.sum(PosSale.total), 0))
        .filter(
            PosSale.pos_session_id == session_id,
            PosSale.status == PosSaleStatus.COMPLETED,
            PosSale.payment_method == PaymentMethod.CASH.value,
        )
        .scalar()
    )

    session.closing_cash = closing_cash
    session.expected_cash = session.opening_cash + Decimal(str(total_cash_sales))
    session.cash_difference = closing_cash - session.expected_cash
    session.closed_by_user_id = closed_by_user_id
    session.closed_at = datetime.now(timezone.utc)
    session.status = PosSessionStatus.CLOSED
    if notes:
        session.notes = (session.notes or "") + f"\nClose notes: {notes}"
    db.session.commit()
    return session


def void_session(session_id: int) -> PosSession:
    session = db.session.get(PosSession, session_id)
    if not session:
        raise ValueError("Session not found")
    session.status = PosSessionStatus.VOIDED
    db.session.commit()
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
            variant_id=item_data.get("variant_id"),
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
            variant_id=item_data.get("variant_id"),
            quantity=item_data["quantity"],
            unit_price=Decimal(str(item_data["unit_price"])),
            line_total=pos_item.line_total,
            is_custom_item=item_data.get("item_type", "product") != "product",
            custom_description=item_data.get("description") if item_data.get("item_type") != "product" else None,
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
    db.session.commit()

    _deduct_inventory_for_sale(sale)

    return sale, order


def _deduct_inventory_for_sale(sale: PosSale) -> None:
    for item in sale.items:
        if item.item_type != PosSaleItemType.PRODUCT or item.product_id is None:
            continue
        records = InventoryRecord.query.filter(
            InventoryRecord.variant_id == item.variant_id,
            InventoryRecord.product_id == item.product_id,
            InventoryRecord.quantity_on_hand > 0,
        ).order_by(InventoryRecord.id).all()

        remaining = item.quantity
        for rec in records:
            if remaining <= 0:
                break
            deduct = min(remaining, rec.quantity_on_hand)
            rec.quantity_on_hand -= deduct
            remaining -= deduct


def get_session_summary(session_id: int) -> dict:
    session = db.session.get(PosSession, session_id)
    if not session:
        raise ValueError("Session not found")

    sales = PosSale.query.filter_by(pos_session_id=session_id, status=PosSaleStatus.COMPLETED).all()
    total_sales = sum(s.total for s in sales)
    payment_totals: dict[str, Decimal] = {}
    for s in sales:
        pm = str(s.payment_method)
        payment_totals[pm] = payment_totals.get(pm, Decimal("0")) + s.total

    cash_sales_total = sum(s.total for s in sales if s.payment_method == PaymentMethod.CASH.value)
    expected_cash = session.opening_cash + Decimal(str(cash_sales_total))

    return {
        "session": session,
        "sales": sales,
        "total_sales": total_sales,
        "sale_count": len(sales),
        "payment_totals": payment_totals,
        "expected_cash": expected_cash,
    }
