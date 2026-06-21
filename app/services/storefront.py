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
    ProductVariant,
)

CART_SESSION_KEY = "public_cart"
UNLIMITED_STOCK = 9999


class StorefrontError(RuntimeError):
    pass


@dataclass(frozen=True)
class CartLine:
    key: str
    product: Product
    variant: ProductVariant | None
    quantity: int
    unit_price: Decimal
    line_total: Decimal
    available_stock: int | None

    @property
    def display_name(self) -> str:
        if self.variant:
            return f"{self.product.name} - {self.variant.name}"
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


def cart_item_key(product_id: int, variant_id: int | None) -> str:
    return f"{product_id}:{variant_id or 0}"


def square_checkout_available(config: dict) -> bool:
    return bool(config.get("SQUARE_ACCESS_TOKEN") and config.get("SQUARE_LOCATION_ID"))


def is_product_purchasable(product: Product) -> bool:
    return (
        product.is_public
        and product.deleted_at is None
        and product.status.value == "active"
    )


def active_variants(product: Product) -> list[ProductVariant]:
    return [variant for variant in product.variants if variant.active]


def variant_choices(product: Product) -> list[tuple[int, str]]:
    return [(variant.id, variant.name) for variant in active_variants(product)]


def product_stock(product: Product, variant: ProductVariant | None = None) -> int | None:
    query = (
        select(func.coalesce(func.sum(InventoryRecord.quantity_on_hand - InventoryRecord.quantity_reserved), 0))
        .where(InventoryRecord.product_id == product.id)
    )
    if variant is None:
        query = query.where(InventoryRecord.variant_id.is_(None))
    else:
        query = query.where(InventoryRecord.variant_id == variant.id)

    available = db.session.scalar(query)
    has_records_query = select(func.count(InventoryRecord.id)).where(InventoryRecord.product_id == product.id)
    if variant is None:
        has_records_query = has_records_query.where(InventoryRecord.variant_id.is_(None))
    else:
        has_records_query = has_records_query.where(InventoryRecord.variant_id == variant.id)
    record_count = db.session.scalar(has_records_query) or 0

    if record_count == 0 or product.product_type in {
        ProductType.MADE_TO_ORDER_PRODUCT,
        ProductType.CUSTOMIZABLE_PRODUCT,
        ProductType.B2B_PRODUCT,
    }:
        return None

    return int(available or 0)


def available_stock_label(product: Product, variant: ProductVariant | None = None) -> str:
    available = product_stock(product, variant)
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

        variant = None
        variant_id = int(item.get("variant_id") or 0)
        if variant_id:
            variant = db.session.get(ProductVariant, variant_id)
            if variant is None or variant.product_id != product.id or not variant.active:
                continue

        unit_price = variant.price if variant else product.base_price
        quantity = max(1, int(item.get("quantity", 1)))
        lines.append(
            CartLine(
                key=cart_item_key(product.id, variant.id if variant else None),
                product=product,
                variant=variant,
                quantity=quantity,
                unit_price=unit_price,
                line_total=unit_price * quantity,
                available_stock=product_stock(product, variant),
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


def add_to_cart(product: Product, variant_id: int | None, quantity: int) -> None:
    if not is_product_purchasable(product):
        raise StorefrontError("That product is not available right now.")

    variant = None
    product_variants = active_variants(product)
    if product_variants:
        if not variant_id:
            raise StorefrontError("Please choose an option before adding this item to your cart.")
        variant = db.session.get(ProductVariant, variant_id)
        if variant is None or variant.product_id != product.id or not variant.active:
            raise StorefrontError("That product option is no longer available.")

    available = product_stock(product, variant)
    if available is not None and quantity > available:
        raise StorefrontError("We don't have that many available right now.")

    cart = get_raw_cart()
    key = cart_item_key(product.id, variant.id if variant else None)
    for item in cart:
        if cart_item_key(int(item["product_id"]), int(item.get("variant_id") or 0) or None) == key:
            new_quantity = int(item.get("quantity", 1)) + quantity
            if available is not None and new_quantity > available:
                raise StorefrontError("We don't have that many available right now.")
            item["quantity"] = new_quantity
            store_raw_cart(cart)
            return

    cart.append({"product_id": product.id, "variant_id": variant.id if variant else None, "quantity": quantity})
    store_raw_cart(cart)


def update_cart_line(line_key: str, quantity: int) -> None:
    cart = get_raw_cart()
    updated: list[dict] = []
    for item in cart:
        current_key = cart_item_key(int(item["product_id"]), int(item.get("variant_id") or 0) or None)
        if current_key == line_key:
            if quantity <= 0:
                continue
            product = db.session.get(Product, int(item["product_id"]))
            variant = db.session.get(ProductVariant, int(item["variant_id"])) if item.get("variant_id") else None
            if product is None or not is_product_purchasable(product):
                continue
            available = product_stock(product, variant)
            if available is not None and quantity > available:
                raise StorefrontError("We don't have that many available right now.")
            item["quantity"] = quantity
        updated.append(item)
    store_raw_cart(updated)


def remove_cart_line(line_key: str) -> None:
    cart = [
        item
        for item in get_raw_cart()
        if cart_item_key(int(item["product_id"]), int(item.get("variant_id") or 0) or None) != line_key
    ]
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


def reserve_inventory(lines: list[CartLine]) -> None:
    for line in lines:
        if line.available_stock is None:
            continue
        remaining = line.quantity
        records = (
            InventoryRecord.query.filter_by(
                product_id=line.product.id,
                variant_id=line.variant.id if line.variant else None,
            )
            .order_by(InventoryRecord.quantity_on_hand.desc())
            .all()
        )
        for record in records:
            if remaining <= 0:
                break
            available_here = max(0, record.quantity_on_hand - record.quantity_reserved)
            if available_here <= 0:
                continue
            reserve = min(available_here, remaining)
            record.quantity_reserved += reserve
            remaining -= reserve

        if remaining > 0:
            raise StorefrontError("One of the items in your cart just sold out. Please review your cart and try again.")


def create_online_order(
    *,
    first_name: str,
    last_name: str,
    email: str,
    phone: str | None,
    notes: str | None,
    fulfillment_method: str,
    payment_option: str,
    shipping: dict,
    config: dict,
) -> Order:
    summary = build_cart_summary(config, fulfillment_method=fulfillment_method)
    if not summary.lines:
        raise StorefrontError("Your cart is empty.")

    for line in summary.lines:
        if line.available_stock is not None and line.quantity > line.available_stock:
            raise StorefrontError(f"{line.display_name} is no longer available in that quantity.")

    customer = upsert_customer(first_name, last_name, email, phone, shipping)
    order = Order(
        customer=customer,
        status=OrderStatus.PENDING,
        source=OrderSource.ONLINE,
        payment_status=OrderPaymentStatus.PENDING,
        fulfillment_method=OrderFulfillmentMethod(fulfillment_method),
        notes=notes.strip() if notes else None,
        customer_name=f"{first_name.strip()} {last_name.strip()}".strip(),
        customer_email=email.strip().lower(),
        customer_phone=phone.strip() if phone else None,
        shipping_name=shipping.get("shipping_name"),
        shipping_address_line_1=shipping.get("shipping_address_line_1"),
        shipping_address_line_2=shipping.get("shipping_address_line_2"),
        shipping_city=shipping.get("shipping_city"),
        shipping_state=shipping.get("shipping_state"),
        shipping_postal_code=shipping.get("shipping_postal_code"),
        subtotal=summary.subtotal,
        shipping_total=summary.shipping_total,
        total=summary.total,
        paid_amount=Decimal("0.00"),
        payment_provider=payment_option,
        external_payment_reference=config.get("SHOP_VENMO_HANDLE") if payment_option == "venmo" else None,
    )
    db.session.add(order)
    db.session.flush()

    for line in summary.lines:
        db.session.add(
            OrderItem(
                order=order,
                product_id=line.product.id,
                variant_id=line.variant.id if line.variant else None,
                quantity=line.quantity,
                unit_price=line.unit_price,
                line_total=line.line_total,
                is_custom_item=False,
                notes="Public storefront checkout",
            )
        )

    reserve_inventory(summary.lines)
    db.session.commit()
    return order
