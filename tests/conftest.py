from __future__ import annotations

from pathlib import Path

import pytest

from app import create_app
from app.extensions import db
from app.models import Category, Collection, Product, ProductStatus, ProductType, User, UserRole
from app.services.api_tokens import create_api_token


@pytest.fixture()
def app(tmp_path: Path):
    database_path = tmp_path / "test.db"
    upload_path = tmp_path / "uploads"

    app = create_app(
        "testing",
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
            "UPLOAD_FOLDER": str(upload_path),
            "ADMIN_EMAIL": "admin@example.com",
            "ADMIN_PASSWORD": "change-me-now",
            "SERVER_NAME": "localhost.localdomain",
        },
    )

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def runner(app):
    return app.test_cli_runner()


@pytest.fixture()
def admin_user(app):
    with app.app_context():
        user = User(
            email="owner@example.com",
            first_name="Dude",
            last_name="Fish",
            role=UserRole.ADMIN,
            is_active=True,
        )
        user.set_password("super-secret")
        db.session.add(user)
        db.session.commit()
        return {
            "email": user.email,
            "password": "super-secret",
            "id": user.id,
        }


@pytest.fixture()
def login_admin(client, admin_user):
    client.post(
        "/auth/login",
        data={
            "email": admin_user["email"],
            "password": admin_user["password"],
        },
    )
    return admin_user


@pytest.fixture()
def catalog_product(app):
    with app.app_context():
        category = Category(
            name="Dragons",
            slug="dragons",
            description="Dragons",
            sort_order=10,
            is_public=True,
            is_pos_visible=True,
        )
        collection = Collection(
            name="The Dragon Den",
            slug="the-dragon-den",
            description="Featured dragons",
            is_public=True,
            sort_order=10,
        )
        product = Product(
            name="Rainbow Dragon",
            slug="rainbow-dragon",
            sku_base="DRG-RAINBOW",
            short_description="A colorful articulated dragon.",
            description="A colorful articulated dragon.",
            category=category,
            collection=collection,
            product_type=ProductType.FINISHED_GOOD,
            status=ProductStatus.ACTIVE,
            is_public=True,
            is_pos_visible=True,
            is_featured=True,
            base_price=28,
            estimated_material_cost=3,
            estimated_labor_minutes=12,
            estimated_print_minutes=180,
            estimated_profit=25,
        )
        db.session.add_all([category, collection, product])
        db.session.commit()
        return product.id


@pytest.fixture()
def api_token(app):
    with app.app_context():
        user = User(
            email="api-owner@example.com",
            first_name="API",
            last_name="Owner",
            role=UserRole.ADMIN,
            is_active=True,
        )
        user.set_password("super-secret")
        db.session.add(user)
        db.session.commit()
        _, raw_token = create_api_token(user, "Phase 2 Test Token", scopes=["catalog"])
        return raw_token
