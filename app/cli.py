from __future__ import annotations

import click
from flask import current_app

from app.services.demo_seed import seed_demo_data
from app.services.users import ensure_admin_user


@click.group("seed")
def seed_group() -> None:
    """Seed foundational data."""


@seed_group.command("admin")
def seed_admin() -> None:
    """Create the initial admin user from environment values."""
    email = current_app.config["ADMIN_EMAIL"]
    password = current_app.config["ADMIN_PASSWORD"]

    if not email or not password:
        raise click.ClickException("ADMIN_EMAIL and ADMIN_PASSWORD must be configured.")

    user, created = ensure_admin_user(
        email=email,
        password=password,
        first_name="Admin",
        last_name="User",
    )

    if created:
        click.echo(f"Created admin user: {user.email}")
        return

    click.echo(f"Admin user already exists: {user.email}")


@seed_group.command("demo")
def seed_demo() -> None:
    """Create Phase 3 demo data (catalog, fleet, orders, customers, print jobs)."""
    counts = seed_demo_data(
        admin_email=current_app.config["ADMIN_EMAIL"],
        admin_password=current_app.config["ADMIN_PASSWORD"],
    )
    click.echo("Demo seed complete.")
    for key, value in counts.items():
        click.echo(f"- {key}: {value}")
