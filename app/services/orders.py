from __future__ import annotations

from decimal import Decimal

from app.extensions import db
from app.models import (
    CustomRequest,
    CustomRequestStatus,
    Customer,
    Order,
    OrderItem,
    OrderSource,
    OrderStatus,
    Payment,
    PaymentMethod,
)


def convert_custom_request_to_order(
    custom_request: CustomRequest,
    total: Decimal,
    deposit_amount: Decimal = Decimal("0"),
    deposit_method: PaymentMethod = PaymentMethod.CASH,
    internal_notes: str | None = None,
) -> Order:
    customer = None
    if custom_request.email:
        customer = Customer.query.filter_by(email=custom_request.email).first()
    if customer is None:
        name = (custom_request.name or "").strip()
        name_parts = name.split(" ", 1) if " " in name else [name, ""]
        customer = Customer(
            first_name=name_parts[0] or name,
            last_name=name_parts[1] if len(name_parts) > 1 else "",
            email=custom_request.email or None,
            phone=custom_request.phone,
        )
        db.session.add(customer)
        db.session.flush()

    order = Order(
        customer=customer,
        source=OrderSource.CUSTOM,
        status=OrderStatus.PENDING,
        subtotal=total,
        total=total,
        paid_amount=deposit_amount,
        internal_notes=internal_notes,
    )
    db.session.add(order)
    db.session.flush()

    item = OrderItem(
        order=order,
        is_custom_item=True,
        custom_description=custom_request.description,
        quantity=1,
        unit_price=total,
        line_total=total,
    )
    db.session.add(item)
    db.session.flush()

    if deposit_amount > 0:
        payment = Payment(
            order=order,
            amount=deposit_amount,
            method=deposit_method,
            notes="Deposit for custom order",
        )
        db.session.add(payment)

    custom_request.converted_to_order_id = order.id
    custom_request.customer_id = customer.id
    custom_request.status = CustomRequestStatus.DEPOSIT_COLLECTED
    db.session.commit()

    return order
