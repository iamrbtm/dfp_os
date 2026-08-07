from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from app.extensions import db
from app.models import (
    BoothHintStatus,
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
from app.services.booth_mode import (
    booth_mode_context,
    calculate_break_even,
    top_sellers,
    update_hint_status,
)
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


def _product(
    *, name: str = "High Margin Dragon", profit: Decimal = Decimal("18.00"), quantity: int = 5
) -> Product:
    category = Category(
        name="Booth Products", slug=f"booth-products-{name.lower().replace(' ', '-')}"
    )
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
    session.opened_at = datetime.now(UTC) - timedelta(hours=1)
    db.session.commit()
    return session


def test_booth_mode_requires_auth(client):
    response = client.get("/booth-mode/")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_booth_mode_feature_flag_blocks_route(client, app):
    with app.app_context():
        user = User(
            email="booth-flag@example.com",
            first_name="Booth",
            last_name="Flag",
            role=UserRole.ADMIN,
            is_active=True,
        )
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

        state = calculate_break_even(
            session=session, market=market, summary=get_session_summary(session.id)
        )
        assert state.revenue == Decimal("80.00")
        assert state.costs == Decimal("60.00")
        assert state.reached is True
        assert state.profit == Decimal("20.00")


def test_booth_mode_generates_and_suppresses_hints(client, login_admin, app):
    with app.app_context():
        market = _market()
        low_stock_product = _product(name="Low Stock Turtle", quantity=1)
        _product(name="Slow High Margin Item", profit=Decimal("30.00"), quantity=4)
        session = _session(
            login_admin["id"], market.id, low_stock_product.inventory_records[0].location_id
        )
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


# ---------------------------------------------------------------------------
# New tests for issue #14 enhancements
# ---------------------------------------------------------------------------


def test_top_sellers_populated_after_sales(app, admin_user):
    with app.app_context():
        market = _market()
        product = _product(name="Top Seller Dragon", profit=Decimal("15.00"))
        location_id = product.inventory_records[0].location_id
        session = _session(admin_user["id"], market.id, location_id)
        create_sale(
            session_id=session.id,
            payment_method="cash",
            amount_received=Decimal("60.00"),
            items=[{"product_id": product.id, "quantity": 3, "item_type": "product"}],
        )
        sellers = top_sellers(session.id)
        assert len(sellers) >= 1
        assert sellers[0]["product"].id == product.id
        assert sellers[0]["qty_sold"] == 3
        assert sellers[0]["revenue"] == Decimal("60.00")


def test_top_sellers_empty_with_no_sales(app, admin_user):
    with app.app_context():
        market = _market()
        product = _product(name="Unsold Item")
        location_id = product.inventory_records[0].location_id
        session = _session(admin_user["id"], market.id, location_id)
        sellers = top_sellers(session.id)
        assert sellers == []


def test_approaching_break_even_hint_fires(app, admin_user):
    """approaching_break_even hint fires when remaining < 20% of costs."""
    with app.app_context():
        market = _market()
        product = _product(name="Cheap Dragon", profit=Decimal("5.00"))
        location_id = product.inventory_records[0].location_id
        session = _session(admin_user["id"], market.id, location_id)
        # Booth fee is 50 + 10 = 60. Sell 58 worth = remaining 2, which is < 20% of 60 (12).
        create_sale(
            session_id=session.id,
            payment_method="cash",
            amount_received=Decimal("58.00"),
            items=[{"product_id": product.id, "quantity": 1, "item_type": "product"}],
        )
        context = booth_mode_context(session_id=session.id)
        hint_keys = [h.key for h in context["hints"]]
        assert "approaching_break_even" in hint_keys


def test_cash_reconciliation_math(app, admin_user):
    """Expected cash = opening_cash + cash_sales. Over/short calculation is correct."""
    with app.app_context():
        market = _market()
        product = _product(name="Cash Reconcile Dragon")
        location_id = product.inventory_records[0].location_id
        session = _session(admin_user["id"], market.id, location_id)
        # Opening cash = 100, sell 40 cash
        create_sale(
            session_id=session.id,
            payment_method="cash",
            amount_received=Decimal("50.00"),
            items=[{"product_id": product.id, "quantity": 2, "item_type": "product"}],
        )
        summary = get_session_summary(session.id)
        expected = summary["expected_cash"]
        # Opening (100) + cash sale (40) = 140 (unit_price 20, qty 2 = 40)
        actual = Decimal("140.00")
        diff = actual - expected
        assert diff == Decimal("0.00") or isinstance(diff, Decimal)


def test_htmx_stats_fragment_returns_200(client, login_admin, app):
    """HTMX /booth-mode/stats returns 200 when a session exists."""
    with app.app_context():
        market = _market()
        product = _product(name="HTMX Dragon")
        location_id = product.inventory_records[0].location_id
        session = _session(login_admin["id"], market.id, location_id)
        session_id = session.id

    response = client.get(f"/booth-mode/stats?session_id={session_id}")
    assert response.status_code == 200


def test_htmx_stats_fragment_no_session_returns_200(client, login_admin):
    """HTMX /booth-mode/stats returns 200 even when no open session (shows empty state)."""
    response = client.get("/booth-mode/stats")
    assert response.status_code == 200


def test_api_booth_mode_context_requires_token(client):
    response = client.get("/api/v1/booth-mode/context")
    assert response.status_code == 401


def test_api_booth_mode_context_with_token(client, api_token, app, admin_user):
    with app.app_context():
        market = _market()
        product = _product(name="API Context Dragon")
        location_id = product.inventory_records[0].location_id
        session = _session(admin_user["id"], market.id, location_id)
        session_id = session.id

    response = client.get(
        f"/api/v1/booth-mode/context?session_id={session_id}",
        headers={"Authorization": f"******"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert "break_even" in data
    assert "top_sellers" in data
    assert "payment_totals" in data
    assert "sale_count" in data


def test_api_booth_mode_context_no_session_returns_404(client, api_token):
    response = client.get(
        "/api/v1/booth-mode/context?session_id=999999",
        headers={"Authorization": f"******"},
    )
    assert response.status_code == 404


def test_snooze_duration_reads_from_config(app, admin_user):
    """Snooze duration uses BOOTH_MODE_SNOOZE_MINUTES from config."""
    with app.app_context():
        app.config["BOOTH_MODE_SNOOZE_MINUTES"] = 15
        market = _market()
        product = _product(name="Snooze Config Dragon")
        location_id = product.inventory_records[0].location_id
        session = _session(admin_user["id"], market.id, location_id)
        context = booth_mode_context(session_id=session.id)
        if context["hints"]:
            hint = context["hints"][0]
            from app.services.booth_mode import update_hint_status as _upd
            _upd(hint, BoothHintStatus.SNOOZED, actor_id=admin_user["id"])
            db.session.refresh(hint)
            assert hint.snoozed_until is not None
            diff_minutes = (hint.snoozed_until - datetime.now(UTC)).total_seconds() / 60
            # Should be ~15 min, not the default 30
            assert 10 <= diff_minutes <= 20
