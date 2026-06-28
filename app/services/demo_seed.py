from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models import (
    Business,
    Category,
    Collection,
    Customer,
    Expense,
    ExpenseCategory,
    FeatureFlag,
    FilamentSpool,
    FilamentStatus,
    InventoryLocation,
    InventoryRecord,
    Market,
    MarketPackingList,
    MarketStatus,
    Order,
    OrderItem,
    OrderPaymentStatus,
    OrderSource,
    OrderStatus,
    Payment,
    PaymentMethod,
    PosSale,
    PosSaleItem,
    PosSaleItemType,
    PosSaleStatus,
    PosSession,
    PosSessionStatus,
    PrepTask,
    PrepTaskCategory,
    PrepTaskStatus,
    Printer,
    PrinterStatus,
    PrintJob,
    PrintJobStatus,
    Product,
    ProductStatus,
    ProductType,
    User,
    UserRole,
)
from app.services.users import ensure_admin_user


def _upsert(model, defaults: dict | None = None, **lookup):
    instance = model.query.filter_by(**lookup).first()
    if instance is None:
        instance = model(**lookup)
        db.session.add(instance)
    for key, value in (defaults or {}).items():
        setattr(instance, key, value)
    db.session.flush()
    return instance


def seed_demo_data(*, admin_email: str, admin_password: str) -> dict[str, int]:
    business = _upsert(
        Business,
        slug="dude-fish-printing",
        defaults={
            "name": "Dude Fish Printing",
            "public_name": "Dude Fish Printing",
            "timezone": "America/Chicago",
            "currency": "USD",
            "is_active": True,
        },
    )

    admin_user, _ = ensure_admin_user(
        email=admin_email,
        password=admin_password,
        first_name="Admin",
        last_name="User",
    )

    staff_user = User.query.filter_by(email="staff@example.com").first()
    if staff_user is None:
        staff_user = User(
            email="staff@example.com",
            first_name="Staff",
            last_name="User",
            role=UserRole.STAFF,
            is_active=True,
        )
        staff_user.set_password("change-me-now")
        db.session.add(staff_user)
        db.session.flush()
    else:
        staff_user.first_name = "Staff"
        staff_user.last_name = "User"
        staff_user.role = UserRole.STAFF
        staff_user.is_active = True

    dragons = _upsert(Category, slug="dragons", defaults={"name": "Dragons", "is_public": True, "is_pos_visible": True})
    fidgets = _upsert(Category, slug="fidgets", defaults={"name": "Fidgets", "is_public": True, "is_pos_visible": True})
    local = _upsert(Category, slug="clarksville", defaults={"name": "Clarksville", "is_public": True, "is_pos_visible": True})

    summer = _upsert(Collection, slug="summer-best-sellers", defaults={"name": "Summer Best Sellers", "is_public": True})
    market = _upsert(Collection, slug="market-favorites", defaults={"name": "Market Favorites", "is_public": True})

    demo_products = [
        {
            "slug": "rainbow-dragon",
            "name": "Rainbow Dragon",
            "sku_base": "DRG-RAINBOW",
            "category_id": dragons.id,
            "collection_id": summer.id,
            "base_price": Decimal("25.00"),
        },
        {
            "slug": "fidget-slider",
            "name": "Fidget Slider",
            "sku_base": "FGT-SLIDER",
            "category_id": fidgets.id,
            "collection_id": market.id,
            "base_price": Decimal("8.00"),
        },
        {
            "slug": "clarksville-magnet",
            "name": "Clarksville TN Magnet",
            "sku_base": "CLK-MAGNET",
            "category_id": local.id,
            "collection_id": market.id,
            "base_price": Decimal("6.00"),
        },
        {
            "slug": "custom-order-deposit",
            "name": "Custom Order Deposit",
            "sku_base": "CUSTOM-DEPOSIT",
            "category_id": local.id,
            "collection_id": None,
            "base_price": Decimal("20.00"),
            "product_type": ProductType.CUSTOMIZABLE_PRODUCT,
        },
    ]

    products: list[Product] = []
    for payload in demo_products:
        product = _upsert(
            Product,
            slug=payload["slug"],
            defaults={
                "business_id": business.id,
                "name": payload["name"],
                "sku_base": payload["sku_base"],
                "category_id": payload["category_id"],
                "collection_id": payload["collection_id"],
                "product_type": payload.get("product_type", ProductType.FINISHED_GOOD),
                "status": ProductStatus.ACTIVE,
                "is_public": True,
                "is_pos_visible": True,
                "base_price": payload["base_price"],
                "estimated_material_cost": payload["base_price"] * Decimal("0.22"),
                "estimated_profit": payload["base_price"] * Decimal("0.46"),
                "estimated_print_minutes": 180,
                "estimated_labor_minutes": 15,
                "license_status": "commercial_allowed",
                "design_source": "Product Studio demo seed",
                "model_notes": f"{payload['name']} master file",
            },
        )
        products.append(product)

    printers = [
        ("A1-01", "Bambu A1"),
        ("A1-02", "Bambu A1"),
        ("X1C-01", "Bambu X1 Carbon"),
    ]
    for name, model in printers:
        _upsert(
            Printer,
            name=name,
            defaults={
                "business_id": business.id,
                "model": model,
                "status": PrinterStatus.ACTIVE,
                "has_ams": model != "Bambu A1",
            },
        )

    filament = _upsert(
        FilamentSpool,
        brand="Bambu Lab",
        material_type="PLA",
        color_name="Teal",
        defaults={
            "business_id": business.id,
            "status": FilamentStatus.ACTIVE,
            "spool_weight_grams": 1000,
            "remaining_weight_grams": 720,
            "cost_per_spool": Decimal("22.00"),
            "cost_per_gram": Decimal("0.0220"),
        },
    )

    studio = _upsert(
        InventoryLocation,
        name="Studio Shelf",
        defaults={"business_id": business.id, "type": "storage", "active": True},
    )
    market_bin = _upsert(
        InventoryLocation,
        name="Market Bin",
        defaults={"business_id": business.id, "type": "market", "active": True},
    )

    for product, qty in zip(products, [14, 36, 20, 0], strict=False):
        _upsert(
            InventoryRecord,
            product_id=product.id,
            location_id=studio.id,
            defaults={
                "business_id": business.id,
                "quantity_on_hand": qty,
                "quantity_reserved": 0,
                "reorder_threshold": 4,
                "reorder_target": 20,
            },
        )

    customer = _upsert(
        Customer,
        email="demo.customer@example.com",
        defaults={
            "business_id": business.id,
            "first_name": "Demo",
            "last_name": "Customer",
            "phone": "555-0101",
            "is_active": True,
        },
    )

    market_event = _upsert(
        Market,
        name="Clarksville Makers Market",
        defaults={
            "business_id": business.id,
            "status": MarketStatus.SCHEDULED,
            "event_date": date.today(),
            "city": "Clarksville",
            "state": "TN",
            "booth_fee": Decimal("45.00"),
        },
    )

    for product, planned in zip(products[:3], [6, 15, 10], strict=False):
        _upsert(
            MarketPackingList,
            market_id=market_event.id,
            product_id=product.id,
            defaults={"planned_quantity": planned, "packed_quantity": 0, "sold_quantity": 0, "returned_quantity": 0},
        )

    pos_session = _upsert(
        PosSession,
        session_number="POS-DEMO-001",
        defaults={
            "business_id": business.id,
            "opened_by_user_id": admin_user.id,
            "inventory_location_id": market_bin.id,
            "market_id": market_event.id,
            "status": PosSessionStatus.OPEN,
            "opening_cash": Decimal("100.00"),
        },
    )

    order = _upsert(
        Order,
        order_number="DFP-DEMO-ORDER",
        defaults={
            "business_id": business.id,
            "customer_id": customer.id,
            "status": OrderStatus.COMPLETED,
            "source": OrderSource.POS,
            "payment_status": OrderPaymentStatus.PAID,
            "market_id": market_event.id,
            "pos_session_id": pos_session.id,
            "subtotal": Decimal("25.00"),
            "tax_total": Decimal("0.00"),
            "discount_total": Decimal("0.00"),
            "total": Decimal("25.00"),
            "paid_amount": Decimal("25.00"),
        },
    )
    _upsert(
        OrderItem,
        order_id=order.id,
        product_id=products[0].id,
        defaults={
            "quantity": 1,
            "unit_price": Decimal("25.00"),
            "line_total": Decimal("25.00"),
        },
    )
    _upsert(
        Payment,
        order_id=order.id,
        reference="DEMO-CASH",
        defaults={
            "amount": Decimal("25.00"),
            "method": PaymentMethod.CASH,
        },
    )

    sale = _upsert(
        PosSale,
        sale_number="SALE-DEMO-001",
        defaults={
            "pos_session_id": pos_session.id,
            "order_id": order.id,
            "customer_id": customer.id,
            "subtotal": Decimal("25.00"),
            "discount_total": Decimal("0.00"),
            "tax_total": Decimal("0.00"),
            "total": Decimal("25.00"),
            "payment_method": PaymentMethod.CASH.value,
            "amount_received": Decimal("30.00"),
            "change_due": Decimal("5.00"),
            "status": PosSaleStatus.COMPLETED,
        },
    )
    _upsert(
        PosSaleItem,
        pos_sale_id=sale.id,
        product_id=products[0].id,
        description=products[0].name,
        defaults={
            "quantity": 1,
            "unit_price": Decimal("25.00"),
            "discount_amount": Decimal("0.00"),
            "line_total": Decimal("25.00"),
            "item_type": PosSaleItemType.PRODUCT,
        },
    )

    _upsert(
        PrintJob,
        label="Demo rainbow dragon run",
        defaults={
            "product_id": products[0].id,
            "status": PrintJobStatus.QUEUED,
            "estimated_minutes": 185,
        },
    )

    _upsert(
        Expense,
        vendor="Market Organizer",
        date=date.today(),
        defaults={
            "business_id": business.id,
            "category": ExpenseCategory.BOOTH_FEES,
            "amount": Decimal("45.00"),
            "related_market_id": market_event.id,
        },
    )

    _upsert(
        PrepTask,
        title="Pack market starter kit",
        defaults={
            "business_id": business.id,
            "market_id": market_event.id,
            "category": PrepTaskCategory.MARKET_SETUP,
            "status": PrepTaskStatus.OPEN,
        },
    )

    _upsert(
        FeatureFlag,
        key="module.products.enabled",
        defaults={"business_id": business.id, "enabled": True, "description": "Enable Product Studio"},
    )

    db.session.commit()

    return {
        "businesses": Business.query.count(),
        "users": User.query.count(),
        "categories": Category.query.count(),
        "collections": Collection.query.count(),
        "products": Product.query.count(),
        "printers": Printer.query.count(),
        "filament_spools": FilamentSpool.query.count(),
        "inventory_locations": InventoryLocation.query.count(),
        "inventory_records": InventoryRecord.query.count(),
        "customers": Customer.query.count(),
        "orders": Order.query.count(),
        "pos_sessions": PosSession.query.count(),
        "pos_sales": PosSale.query.count(),
        "markets": Market.query.count(),
        "packing_list_items": MarketPackingList.query.count(),
        "expenses": Expense.query.count(),
        "prep_tasks": PrepTask.query.count(),
        "feature_flags": FeatureFlag.query.count(),
        "filament_cost_per_gram": int(filament.cost_per_gram > 0),
        "staff_users": int(staff_user.id > 0),
    }
