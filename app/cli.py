from __future__ import annotations

import click
from flask import current_app
from pathlib import Path

from app.extensions import db
from app.models.catalog import Product, ProductImage
from app.services.storage import (
    converted_storage_key,
    delete_storage_reference,
    download_storage_bytes,
    gcode_storage_key,
    image_storage_key,
    product_storage_key,
    storage_reference_name,
    upload_bytes_to_storage,
)
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
    from app.services.demo_seed import seed_demo_data

    counts = seed_demo_data(
        admin_email=current_app.config["ADMIN_EMAIL"],
        admin_password=current_app.config["ADMIN_PASSWORD"],
    )
    click.echo("Demo seed complete.")
    for key, value in counts.items():
        click.echo(f"- {key}: {value}")


@seed_group.command("events-2026")
def seed_events_2026_command() -> None:
    """Seed 2026 Clarksville-area events and markets (dummy data based on web research)."""
    from app.services.events_seed import seed_events_2026

    counts = seed_events_2026()
    click.echo("2026 events seed complete.")
    for key, value in counts.items():
        click.echo(f"- {key}: {value}")


@click.group("migrate")
def migrate_group() -> None:
    """Migrate data between versions."""


@migrate_group.command("file-paths")
def migrate_file_paths() -> None:
    """Migrate product asset file paths to the new structured layout.

    Old layout: products/{id}/models|converted|gcode|images/file.ext
    New layout: products/{id}/file.ext
    """
    bucket = current_app.config.get("PRODUCT_ASSETS_BUCKET", "products")
    local_root = current_app.config.get("PRODUCT_ASSETS_PATH", "uploads/products")

    migrated = 0
    errors = 0

    def _migrate_ref(
        ref: str | None,
        *,
        product_id: int,
        storage_key_fn,
    ) -> str | None:
        if not ref:
            return None

        filename = storage_reference_name(ref)
        if not filename:
            return None

        new_key = storage_key_fn(product_id, filename)
        new_ref = (
            f"s3://{bucket}/{new_key}"
            if ref.startswith("s3://")
            else str((Path(local_root) / new_key).resolve())
        )

        if ref == new_ref:
            return None

        try:
            data = download_storage_bytes(ref)
            upload_bytes_to_storage(data, bucket=bucket, key=new_key, local_root=local_root)
            delete_storage_reference(ref)
        except Exception as exc:
            click.echo(f"  Error migrating {ref}: {exc}", err=True)
            return None

        return new_ref

    click.echo("Migrating Product model file paths...")
    for product in db.session.query(Product).all():
        new_file = _migrate_ref(
            product.model_file_path,
            product_id=product.id,
            storage_key_fn=product_storage_key,
        )
        new_converted = _migrate_ref(
            product.converted_model_path,
            product_id=product.id,
            storage_key_fn=converted_storage_key,
        )
        new_gcode = _migrate_ref(
            product.gcode_path,
            product_id=product.id,
            storage_key_fn=gcode_storage_key,
        )

        if new_file or new_converted or new_gcode:
            if new_file:
                product.model_file_path = new_file
            if new_converted:
                product.converted_model_path = new_converted
            if new_gcode:
                product.gcode_path = new_gcode
            migrated += 1

    click.echo("Migrating ProductImage file paths...")
    for img in db.session.query(ProductImage).all():
        new_ref = _migrate_ref(
            img.file_path,
            product_id=img.product_id,
            storage_key_fn=image_storage_key,
        )
        if new_ref:
            img.file_path = new_ref
            migrated += 1

    db.session.commit()
    click.echo(f"\nMigration complete. {migrated} records updated.")
    if errors:
        click.echo(f"{errors} errors occurred (see above).", err=True)
