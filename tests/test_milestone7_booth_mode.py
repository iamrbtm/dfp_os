from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from app.extensions import db
from app.models import (
    Category,
    FeatureFlag,
    InventoryLocation,
    InventoryRecord,
    Market,
    MarketStatus,
    PosSession,
    Product,
    ProductStatus,
    ProductType,
    User,
    UserRole,
)
from app.services.booth_mode import booth_mode_context, calculate_break_even, update_hint_status
from app.models import BoothHintStatus
from app.services.pos import create_sale, get_session_summary, open_session


def _market() -> Market:
    market = Market(
        name="Clarksville Makers Market",
        event_date=date.today(),
        start_time=time(9, 0),
        end_time=(datetime.now() + timedelta(hours=4)).time(),
        status=MarketStatus.SCHEDULED,
        booth_fee=Decimal("50.00"),
        application_fee=Decimal("10.00"),
    )
    db.session.add(market)
    db.session.commit()
    return market


def _product(*, name: str = "High Margin Dragon", profit: Decimal = Decimal("18.00"), quantity: int = 5) -> Product:
    category = Category(name="Booth Products", slug=f"booth-products-{name.lower().replace(' ', '-')}")
    product = Product(
        name=name,
        slug=name.lower().replace(" ", "-"),
        sku_base=name.upper().replace(" ", "-"),
        category=category,
        product_type=ProductType.FINISHED_GOOD,
        status=ProductStatus.ACTIVE,
        is_public=True,
        is_pos_visible=True,
        base_price=Decimal("20.00"),
        estimated_profit=profit,
    )
    location = InventoryLocation.query.filter_by(name="Market Bin").first()
    if location is None:
        location = InventoryLocation(name="Market Bin", type="market_bin")
        db.session.add(location)
        db.session.flush()
    db.session.add_all([category, product])
    db.session.flush()
    db.session.add(
        InventoryRecord(
            product=product,
            location=location,
            quantity_on_hand=quantity,
            reorder_threshold=2,
            reorder_target=8,
        )
    )
    db.session.commit()
    return product


def _session(user_id: int, market_id: int, location_id: int) -> PosSession:
    session = open_session(
        user_id=user_id,
        opening_cash=Decimal("100.00"),
        market_id=market_id,
        inventory_location_id=location_id,
    )
    session.opened_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.session.commit()
    return session


def test_booth_mode_requires_auth(client):
    response = client.get("/booth-mode/")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_booth_mode_feature_flag_blocks_route(client, app):
    with app.app_context():
        user = User(email="booth-flag@example.com", first_name="Booth", last_name="Flag", role=UserRole.ADMIN, is_active=True)
        user.set_password("super-secret")
        db.session.add(user)
        db.session.add(FeatureFlag(key="module.booth_mode.enabled", enabled=False))
        db.session.commit()
    client.post("/auth/login", data={"email": "booth-flag@example.com", "password": "super-secret"})
    response = client.get("/booth-mode/")
    assert response.status_code == 403


def test_booth_break_even_and_profit_tracking(app, admin_user):
    with app.app_context():
        market = _market()
        product = _product()
        location_id = product.inventory_records[0].location_id
        session = _session(admin_user["id"], market.id, location_id)
        create_sale(
            session_id=session.id,
            payment_method="cash",
            amount_received=Decimal("80.00"),
            items=[{"product_id": product.id, "quantity": 4, "item_type": "product"}],
        )

        state = calculate_break_even(session=session, market=market, summary=get_session_summary(session.id))
        assert state.revenue == Decimal("80.00")
        assert state.costs == Decimal("60.00")
        assert state.reached is True
        assert state.profit == Decimal("20.00")


def test_booth_mode_generates_and_suppresses_hints(client, login_admin, app):
    with app.app_context():
        market = _market()
        low_stock_product = _product(name="Low Stock Turtle", quantity=1)
        _product(name="Slow High Margin Item", profit=Decimal("30.00"), quantity=4)
        session = _session(login_admin["id"], market.id, low_stock_product.inventory_records[0].location_id)
        session_id = session.id

    response = client.get(f"/booth-mode/?session_id={session_id}")
    assert response.status_code == 200
    assert b"Booth Mode" in response.data

    with app.app_context():
        context = booth_mode_context(session_id=session_id)
        assert context["hints"]
        hint = context["hints"][0]
        update_hint_status(hint, BoothHintStatus.DISMISSED, actor_id=login_admin["id"])
        dismissed_key = hint.key
        context = booth_mode_context(session_id=session_id)
        assert dismissed_key not in [item.key for item in context["hints"]]
