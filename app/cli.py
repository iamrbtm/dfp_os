from __future__ import annotations

import click
from flask import current_app

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
