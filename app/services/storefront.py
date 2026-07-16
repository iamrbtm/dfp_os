from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from flask import session
from sqlalchemy import func, select

from app.extensions import db
from app.models import (
    Customer,
    InventoryRecord,
    Order,
    OrderFulfillmentMethod,
    OrderItem,
    OrderPaymentStatus,
    OrderSource,
    OrderStatus,
    Product,
    ProductType,
    PickupSlot,
)
from app.services.pickup import assign_order_pickup, validate_pickup_slot

CART_SESSION_KEY = "public_cart"


class StorefrontError(RuntimeError):
    pass


@dataclass(frozen=True)
class CartLine:
    key: str
    product: Product
    quantity: int
    unit_price: Decimal
    line_total: Decimal
    available_stock: int | None

    @property
    def display_name(self) -> str:
        return self.product.name


@dataclass(frozen=True)
class CartSummary:
    lines: list[CartLine]
    subtotal: Decimal
    shipping_total: Decimal
    total: Decimal

    @property
    def item_count(self) -> int:
        return sum(line.quantity for line in self.lines)


def cart_item_key(product_id: int) -> str:
    return str(product_id)


def square_checkout_available(config: dict) -> bool:
    return bool(config.get("SQUARE_ACCESS_TOKEN") and config.get("SQUARE_LOCATION_ID"))


def is_product_purchasable(product: Product) -> bool:
    return product.is_public and product.deleted_at is None and product.status.value == "active"


def product_stock(product: Product) -> int | None:
    query = select(
        func.coalesce(func.sum(InventoryRecord.quantity_on_hand - InventoryRecord.quantity_reserved), 0)
    ).where(InventoryRecord.product_id == product.id)
    available = db.session.scalar(query)
    record_count = db.session.scalar(
        select(func.count(InventoryRecord.id)).where(InventoryRecord.product_id == product.id)
    ) or 0

    if record_count == 0 or product.product_type in {
        ProductType.MADE_TO_ORDER_PRODUCT,
        ProductType.CUSTOMIZABLE_PRODUCT,
        ProductType.B2B_PRODUCT,
    }:
        return None
    return int(available or 0)


def available_stock_label(product: Product) -> str:
    available = product_stock(product)
    if available is None:
        return "Made in small batches"
    if available <= 0:
        return "Currently out of stock"
    if available <= 3:
        return f"Only {available} left"
    return "Ready to ship"


def get_raw_cart() -> list[dict]:
    return list(session.get(CART_SESSION_KEY, []))


def store_raw_cart(items: list[dict]) -> None:
    session[CART_SESSION_KEY] = items
    session.modified = True


def clear_cart() -> None:
    session.pop(CART_SESSION_KEY, None)
    session.modified = True


def resolve_cart_lines(raw_items: list[dict] | None = None) -> list[CartLine]:
    raw_items = raw_items if raw_items is not None else get_raw_cart()
    lines: list[CartLine] = []

    for item in raw_items:
        product = db.session.get(Product, int(item["product_id"]))
        if product is None or not is_product_purchasable(product):
            continue

        quantity = max(1, int(item.get("quantity", 1)))
        unit_price = product.base_price
        lines.append(
            CartLine(
                key=cart_item_key(product.id),
                product=product,
                quantity=quantity,
                unit_price=unit_price,
                line_total=unit_price * quantity,
                available_stock=product_stock(product),
            )
        )

    return lines


def build_cart_summary(config: dict, fulfillment_method: str = "pickup") -> CartSummary:
    lines = resolve_cart_lines()
    subtotal = sum((line.line_total for line in lines), Decimal("0.00"))
    shipping_total = (
        Decimal(config.get("SHOP_DEFAULT_SHIPPING_RATE", Decimal("0.00")))
        if fulfillment_method == OrderFulfillmentMethod.SHIPPING.value and lines
        else Decimal("0.00")
    )
    total = subtotal + shipping_total
    return CartSummary(lines=lines, subtotal=subtotal, shipping_total=shipping_total, total=total)


def add_to_cart(product: Product, quantity: int) -> None:
    if not is_product_purchasable(product):
        raise StorefrontError("That product is not available right now.")

    available = product_stock(product)
    if available is not None and quantity > available:
        raise StorefrontError("We don't have that many available right now.")

    cart = get_raw_cart()
    key = cart_item_key(product.id)
    for item in cart:
        if cart_item_key(int(item["product_id"])) == key:
            new_quantity = int(item.get("quantity", 1)) + quantity
            if available is not None and new_quantity > available:
                raise StorefrontError("We don't have that many available right now.")
            item["quantity"] = new_quantity
            store_raw_cart(cart)
            return

    cart.append({"product_id": product.id, "quantity": quantity})
    store_raw_cart(cart)


def update_cart_line(line_key: str, quantity: int) -> None:
    cart = get_raw_cart()
    updated: list[dict] = []
    for item in cart:
        current_key = cart_item_key(int(item["product_id"]))
        if current_key == line_key:
            if quantity <= 0:
                continue
            product = db.session.get(Product, int(item["product_id"]))
            if product is None or not is_product_purchasable(product):
                continue
            available = product_stock(product)
            if available is not None and quantity > available:
                raise StorefrontError("We don't have that many available right now.")
            item["quantity"] = quantity
        updated.append(item)
    store_raw_cart(updated)


def remove_cart_line(line_key: str) -> None:
    cart = [item for item in get_raw_cart() if cart_item_key(int(item["product_id"])) != line_key]
    store_raw_cart(cart)


def cart_item_count() -> int:
    return sum(line.quantity for line in resolve_cart_lines())


def upsert_customer(first_name: str, last_name: str, email: str, phone: str | None, shipping: dict) -> Customer:
    customer = Customer.query.filter_by(email=email.strip().lower()).first()
    if customer is None:
        customer = Customer(
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            email=email.strip().lower(),
            is_active=True,
        )
        db.session.add(customer)

    customer.first_name = first_name.strip()
    customer.last_name = last_name.strip()
    customer.email = email.strip().lower()
    customer.phone = phone.strip() if phone else None
    customer.address_line_1 = shipping.get("shipping_address_line_1")
    customer.address_line_2 = shipping.get("shipping_address_line_2")
    customer.city = shipping.get("shipping_city")
    customer.state = shipping.get("shipping_state")
    customer.zip_code = shipping.get("shipping_postal_code")
    db.session.flush()
    return customer


def create_order_from_cart(*, customer: Customer, summary: CartSummary, fulfillment_method: str, notes: str | None = None, shipping: dict | None = None) -> Order:
    if not summary.lines:
        raise StorefrontError("Your cart is empty.")

    shipping = shipping or {}

    order = Order(
        customer_id=customer.id,
        status=OrderStatus.PENDING,
        source=OrderSource.ONLINE,
        payment_status=OrderPaymentStatus.UNPAID,
        fulfillment_method=OrderFulfillmentMethod(fulfillment_method),
        customer_name=f"{customer.first_name} {customer.last_name}".strip(),
        customer_email=customer.email,
        customer_phone=customer.phone,
        shipping_name=shipping.get("shipping_name"),
        shipping_address_line_1=shipping.get("shipping_address_line_1") or customer.address_line_1,
        shipping_address_line_2=shipping.get("shipping_address_line_2") or customer.address_line_2,
        shipping_city=shipping.get("shipping_city") or customer.city,
        shipping_state=shipping.get("shipping_state") or customer.state,
        shipping_postal_code=shipping.get("shipping_postal_code") or customer.zip_code,
        subtotal=summary.subtotal,
        shipping_total=summary.shipping_total,
        total=summary.total,
        notes=notes,
    )
    db.session.add(order)
    db.session.flush()

    for line in summary.lines:
        db.session.add(
            OrderItem(
                order_id=order.id,
                product_id=line.product.id,
                quantity=line.quantity,
                unit_price=line.unit_price,
                line_total=line.line_total,
            )
        )

    db.session.commit()
    return order


def create_online_order(
    *,
    first_name: str,
    last_name: str,
    email: str,
    phone: str | None,
    notes: str | None,
    fulfillment_method: str,
    pickup_slot_id: int | None = None,
    payment_option: str,
    shipping: dict,
    config: dict,
) -> Order:
    summary = build_cart_summary(config, fulfillment_method=fulfillment_method)
    if not summary.lines:
        raise StorefrontError("Your cart is empty.")
    slot = None
    if fulfillment_method == OrderFulfillmentMethod.PICKUP.value:
        slot = db.session.get(PickupSlot, pickup_slot_id) if pickup_slot_id else None
        if slot is None:
            raise StorefrontError("Choose an available pickup window.")
        try:
            validate_pickup_slot(slot)
        except ValueError as exc:
            raise StorefrontError(str(exc)) from exc

    customer = upsert_customer(first_name, last_name, email, phone, shipping)
    order = create_order_from_cart(
        customer=customer,
        summary=summary,
        fulfillment_method=fulfillment_method,
        notes=notes,
        shipping=shipping,
    )
    if slot is not None:
        assign_order_pickup(order, slot)
    order.payment_provider = payment_option
    if payment_option != "square":
        order.external_payment_reference = config.get("SHOP_VENMO_HANDLE")
    db.session.commit()
    return order
