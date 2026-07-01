from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

import click
from flask import current_app
from pathlib import Path

from app.extensions import db
from app.models.catalog import Product, ProductImage
from app.models.trend import TrendOpportunityScore, TrendReport
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


@click.group("trend-scout")
def trend_scout_group() -> None:
    """Trend Scout pipeline and analysis."""


@trend_scout_group.command("run")
@click.option("--openai-key", envvar="OPENAI_API_KEY", default="", help="OpenAI API key")
@click.option("--openai-model", envvar="OPENAI_MODEL_TREND_SCOUT", default="gpt-4o-mini", help="OpenAI model")
def trend_scout_run(openai_key: str, openai_model: str) -> None:
    """Run the full Trend Scout pipeline synchronously."""
    from app.services.ai.trend_scout import run_full_pipeline

    click.echo("Starting Trend Scout pipeline...")
    with current_app.app_context():
        result = run_full_pipeline(
            openai_api_key=openai_key,
            openai_model=openai_model,
        )
    if result.get("success"):
        click.echo(f"\nPipeline completed successfully.")
        click.echo(f"  Snapshots stored: {result['total_snapshots']}")
        click.echo(f"  Successful sources: {len(result['successful_sources'])}")
        click.echo(f"  Report ID: {result.get('report_id', 'none')}")
        if result.get("failed_sources"):
            click.echo(f"  Failed sources ({len(result['failed_sources'])}):")
            for src in result["failed_sources"]:
                click.echo(f"    - {src}")
        from app.services.trend_scout_prune import prune_old_data
        prune_result = prune_old_data(dry_run=False)
        if prune_result.get("status") == "pruned":
            click.echo(f"  Auto-prune: removed {prune_result['pruned_reports']} old reports, {prune_result['pruned_snapshots']} snapshots")
    else:
        click.echo(f"\nPipeline failed: {result.get('error', 'unknown error')}", err=True)
        sys.exit(1)


@trend_scout_group.command("status")
def trend_scout_status() -> None:
    """Show the latest Trend Scout report summary."""
    with current_app.app_context():
        report = (
            db.session.query(TrendReport)
            .order_by(TrendReport.report_date.desc())
            .first()
        )
        if not report:
            click.echo("No Trend Reports found. Run `flask trend-scout run` first.")
            return

        click.echo(f"Report #{report.id}")
        click.echo(f"  Date: {report.report_date.isoformat()}")
        click.echo(f"  Summary: {report.summary or 'No summary'}")

        score_count = (
            db.session.query(TrendOpportunityScore)
            .filter(TrendOpportunityScore.report_id == report.id)
            .count()
        )
        click.echo(f"  Opportunity scores: {score_count}")

        from app.models.trend import SourceHealthRecord as SHR

        health_records = (
            db.session.query(SHR)
            .filter(SHR.report_id == report.id)
            .all()
        )
        if health_records:
            click.echo(f"  Source health:")
            for h in health_records:
                status_char = "✓" if h.status == "success" else "✗"
                click.echo(f"    {status_char} {h.source}: {h.status} ({h.item_count} items)" + (f" - {h.error_message}" if h.error_message else ""))
        else:
            click.echo("  Source health: no records")

        from app.models.trend import SourceHealthRecord

        totals = (
            db.session.query(
                SourceHealthRecord.status,
                db.func.count(SourceHealthRecord.id),
            )
            .filter(SourceHealthRecord.report_id == report.id)
            .group_by(SourceHealthRecord.status)
            .all()
        )
        if totals:
            click.echo(f"\n  Source totals:")
            for status, count in totals:
                click.echo(f"    {status}: {count}")


@trend_scout_group.command("backtest")
@click.option("--reports", default=12, help="Number of past reports to evaluate")
@click.option("--sales-window", default=60, help="Sales window in days after each report")
def trend_scout_backtest(reports: int, sales_window: int) -> None:
    """Run Trend Scout backtest from the terminal."""
    from app.services.trend_scout_backtest import run_backtest

    with current_app.app_context():
        result = run_backtest(
            db_session=db.session,
            lookback_reports=reports,
            sales_window_days=sales_window,
        )

    if result.get("status") == "no_data":
        click.echo("No TrendReport records found. Run `flask trend-scout run` first.")
        return

    click.echo(f"Backtest Results ({result['report_count']} reports, {result.get('score_count', 0)} scores)")
    click.echo(f"  Sales window: {sales_window} days")
    click.echo("")
    click.echo("  Prediction Quality:")
    stats = result.get("stats", {})
    for key in ("precision", "recall", "f1_score", "accuracy", "mae", "rmse"):
        val = stats.get(key)
        if val is not None:
            click.echo(f"    {key}: {val:.4f}" if isinstance(val, float) else f"    {key}: {val}")
    click.echo("")
    click.echo("  Component Analysis:")
    for comp in result.get("component_analysis", []):
        click.echo(f"    {comp['component']}: corr={comp.get('correlation', 'N/A')}, predictive_ratio={comp.get('predictive_ratio', 'N/A')}")
    click.echo("")
    click.echo("  Tuning Hints:")
    for hint in result.get("tuning_hints", []):
        click.echo(f"    - {hint}")
    click.echo("")
    if result.get("action_analysis"):
        click.echo("  Action Analysis:")
        for action, data in result["action_analysis"].items():
            click.echo(f"    {action}: count={data.get('count', 0)}, precision={data.get('precision', 'N/A')}")


@trend_scout_group.command("prune")
@click.option("--keep-reports", default=52, help="Number of reports to retain")
@click.option("--keep-days", default=365, help="Max age in days for snapshots")
@click.option("--dry-run", is_flag=True, default=False, help="Show what would be pruned without deleting")
def trend_scout_prune(keep_reports: int, keep_days: int, dry_run: bool) -> None:
    """Prune old Trend Scout data (reports, snapshots, scores, health records)."""
    from app.services.trend_scout_prune import prune_old_data

    with current_app.app_context():
        result = prune_old_data(
            keep_reports=keep_reports,
            keep_days=keep_days,
            dry_run=dry_run,
        )

    if result.get("status") == "none":
        click.echo("No data to prune.")
        return

    label = "Would prune" if dry_run else "Pruned"
    click.echo(f"{label} {result['pruned_reports']} reports, "
               f"{result['pruned_scores']} scores, "
               f"{result['pruned_health_records']} health records, "
               f"{result['pruned_snapshots']} snapshots")
    if dry_run:
        click.echo("(dry run — no data deleted)")
