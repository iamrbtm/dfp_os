"""CLI entry: ``flask --app services.trend-scout:create_app acknowledge-etsy-risk``.

Records the Etsy compliance acknowledgment. The microservice refuses to
start with ``FIRECRAWL_ALLOW_ETSY=true`` unless this file is present.

Usage::

    uv run flask --app services.trend-scout:create_app acknowledge-etsy-risk \
        --note "Read docs/compliance/firecrawl_etsy_opt_in.md 2026-08-13"
"""

from __future__ import annotations

import logging

import click
from flask.cli import with_appcontext

from app.compliance import COMPLIANCE_FILENAME, is_acknowledgment_valid, record_acknowledgment

logger = logging.getLogger(__name__)


@click.command("acknowledge-etsy-risk")
@click.option("--note", required=True, help="Free-text note describing why this acknowledgment is being made.")
@click.option("--operator", default=None, help="Operator name (optional).")
@click.option(
    "--path",
    default=None,
    help="Override the compliance file path. Default is ./compliance/" + COMPLIANCE_FILENAME + ".",
)
@with_appcontext
def acknowledge_etsy_risk(note: str, operator: str | None, path: str | None) -> None:
    """Write the Etsy compliance acknowledgment file."""
    from pathlib import Path

    target = Path(path) if path else None
    written = record_acknowledgment(path=target, note=note, operator=operator)
    valid = is_acknowledgment_valid(written)
    click.echo(f"Wrote {written}")
    click.echo(f"Valid (within 365 days): {valid}")
    if not valid:
        raise click.ClickException("Acknowledgment file failed validation. Inspect the file and re-run.")


def register_cli(app) -> None:
    """Register the Etsy compliance CLI on the Flask app."""
    app.cli.add_command(acknowledge_etsy_risk)
