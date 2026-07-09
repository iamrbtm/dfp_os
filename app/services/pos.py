from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from app.extensions import db
from app.models import Product, ProductStatus
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

MONEY = Decimal("0.01")
MAX_CUSTOM_ITEM_PRICE = Decimal("10000.00")
SELLABLE_PRODUCT_STATUSES = {ProductStatus.ACTIVE, ProductStatus.HIDDEN}
CLIENT_PRICED_ITEM_TYPES = {PosSaleItemType.CUSTOM_ITEM, PosSaleItemType.CUSTOM_DEPOSIT}


def _money(value: object, field_name: str) -> Decimal:
    try:
        amount = Decimal(str(value if value is not None else "0")).quantize(MONEY)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be a valid money amount") from exc
    return amount


def _positive_quantity(value: object) -> int:
    try:
        quantity = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Quantity must be a whole number") from exc
    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero")
    return quantity


def _normalize_sale_item(item_data: dict) -> dict:
    if not isinstance(item_data, dict):
        raise ValueError("Cart item is malformed")

    quantity = _positive_quantity(item_data.get("quantity"))
    discount = _money(item_data.get("discount_amount", 0), "Discount")
    if discount < 0:
        raise ValueError("Discount cannot be negative")

    try:
        item_type = PosSaleItemType(item_data.get("item_type", PosSaleItemType.PRODUCT.value))
    except ValueError as exc:
        raise ValueError("Cart item type is not supported") from exc

    product_id = item_data.get("product_id")
    description = str(item_data.get("description") or "").strip()

    if item_type == PosSaleItemType.PRODUCT:
        if not product_id:
            raise ValueError("Product item is missing a product ID")
        product = db.session.get(Product, product_id)
        if (
            product is None
            or product.deleted_at is not None
            or not product.is_pos_visible
            or product.status not in SELLABLE_PRODUCT_STATUSES
        ):
            raise ValueError("Product is not available for sale")
        unit_price = _money(product.base_price, "Product price")
        if unit_price < 0:
            raise ValueError("Product price cannot be negative")
        description = product.name
    elif item_type in CLIENT_PRICED_ITEM_TYPES:
        unit_price = _money(item_data.get("unit_price"), "Custom item price")
        if unit_price < 0:
            raise ValueError("Custom item price cannot be negative")
        if unit_price > MAX_CUSTOM_ITEM_PRICE:
            raise ValueError("Custom item price exceeds the allowed maximum")
        if not description:
            description = "Custom item" if item_type == PosSaleItemType.CUSTOM_ITEM else "Custom order deposit"
        product_id = None
    else:
        raise ValueError("Cart item type is not supported")

    gross_total = unit_price * quantity
    line_total = gross_total - discount
    if line_total < 0:
        raise ValueError("Line total cannot be negative")

    return {
        "product_id": product_id,
        "quantity": quantity,
        "unit_price": unit_price,
        "discount_amount": discount,
        "line_total": line_total,
        "item_type": item_type,
        "description": description[:255],
        "custom_notes": item_data.get("custom_notes"),
    }


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

    try:
        payment_method_enum = PaymentMethod(payment_method)
    except ValueError as exc:
        raise ValueError("Payment method is not supported") from exc

    amount_received = _money(amount_received, "Amount received")
    if amount_received < 0:
        raise ValueError("Amount received cannot be negative")

    tax_total = _money(tax_total, "Tax total")
    if tax_total < 0:
        raise ValueError("Tax total cannot be negative")

    subtotal = Decimal("0")
    discount_total = Decimal("0")
    normalized_items = [_normalize_sale_item(item_data) for item_data in items]
    if not normalized_items:
        raise ValueError("Cart is empty")

    pos_items = []
    for item_data in normalized_items:
        subtotal += item_data["quantity"] * item_data["unit_price"]
        discount = item_data["discount_amount"]
        discount_total += discount

        pos_item = PosSaleItem(
            product_id=item_data["product_id"],
            quantity=item_data["quantity"],
            unit_price=item_data["unit_price"],
            discount_amount=discount,
            line_total=item_data["line_total"],
            item_type=item_data["item_type"],
            description=item_data["description"],
            custom_notes=item_data["custom_notes"],
        )
        pos_items.append(pos_item)

    total = subtotal - discount_total + tax_total
    if total < 0:
        raise ValueError("Sale total cannot be negative")
    if payment_method_enum == PaymentMethod.CASH and amount_received < total:
        raise ValueError("Cash received must cover the sale total")
    change_due = max(Decimal("0"), amount_received - total)

    order = Order(
        source=OrderSource.POS,
        status=OrderStatus.COMPLETED,
        payment_status=OrderPaymentStatus.PAID,
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

    for item_data, pos_item in zip(normalized_items, pos_items):
        order_item = OrderItem(
            order_id=order.id,
            product_id=item_data["product_id"],
            quantity=item_data["quantity"],
            unit_price=pos_item.unit_price,
            line_total=pos_item.line_total,
            is_custom_item=item_data["item_type"] != PosSaleItemType.PRODUCT,
            custom_description=(
                item_data["description"] if item_data["item_type"] != PosSaleItemType.PRODUCT else None
            ),
        )
        db.session.add(order_item)

    payment_record = Payment(
        order_id=order.id,
        amount=total,
        method=payment_method_enum,
        notes=notes,
        payment_date=datetime.now(timezone.utc),
    )
    db.session.add(payment_record)

    sale = PosSale(
        pos_session_id=session_id,
        order_id=order.id,
        customer_id=customer_id,
        subtotal=subtotal,
        discount_total=discount_total,
        tax_total=tax_total,
        total=total,
        payment_method=payment_method_enum.value,
        amount_received=amount_received,
        change_due=change_due,
        status=PosSaleStatus.COMPLETED,
        notes=notes,
        items=pos_items,
    )
    db.session.add(sale)

    db.session.flush()
    _deduct_inventory_for_sale(sale, session.inventory_location_id, session.opened_by_user_id)
    _update_market_packing_sold(sale, session)

    try:
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
            critical=True,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

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
                "payment_method": payment_method_enum.value,
            },
        )

    return sale, order


def _update_market_packing_sold(sale: PosSale, session: PosSession) -> None:
    if not session.market_id:
        return
    from app.models.market import MarketPackingList
    for item in sale.items:
        if item.item_type != PosSaleItemType.PRODUCT or item.product_id is None:
            continue
        packing = MarketPackingList.query.filter_by(
            market_id=session.market_id,
            product_id=item.product_id,
        ).first()
        if packing:
            packing.sold_quantity = (packing.sold_quantity or 0) + item.quantity


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

    try:
        record_audit_event(
            action="pos_sale.refunded",
            entity_type="pos_sale",
            entity_id=sale.id,
            before_state=before,
            after_state={"status": sale.status.value, "restocked": restock},
            metadata={"notes": notes, "session_id": session.id},
            source_module=__name__,
            actor_id=actor_id,
            critical=True,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return sale
