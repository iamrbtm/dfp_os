"""Compliance acknowledgment for the Firecrawl Etsy tier.

The operator must acknowledge Etsy's Terms of Service risk once before the
microservice boots with ``FIRECRAWL_ALLOW_ETSY=true``. The acknowledgment is
written to ``compliance/etsy_opt_in.json`` and read at boot time.

If the file is missing or stale, the microservice refuses to start with a
clear error. This protects against the env var being checked into a
container image and accidentally enabling Etsy.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

COMPLIANCE_FILENAME = "etsy_opt_in.json"


def default_compliance_path() -> Path:
    """Return the default compliance file path (microservice working dir)."""
    return Path("compliance") / COMPLIANCE_FILENAME


def record_acknowledgment(
    path: Path | None = None,
    note: str = "",
    operator: str | None = None,
) -> Path:
    """Write the compliance acknowledgment file. Returns the path written."""
    target = path or default_compliance_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "acknowledged_at": datetime.now(timezone.utc).isoformat(),
        "operator": operator,
        "note": note,
        "acknowledged_legal_posture": (
            "Operator has read docs/compliance/firecrawl_etsy_opt_in.md and "
            "acknowledges Etsy's ToS risk. Enables FIRECRAWL_ALLOW_ETSY at own risk."
        ),
    }
    target.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return target


def is_acknowledgment_valid(path: Path | None = None) -> bool:
    """Return True if the compliance file exists, parses, and is recent."""
    target = path or default_compliance_path()
    if not target.exists():
        return False
    try:
        payload = json.loads(target.read_text())
    except OSError, json.JSONDecodeError:
        return False
    if not isinstance(payload, dict):
        return False
    acknowledged_at = payload.get("acknowledged_at")
    if not isinstance(acknowledged_at, str):
        return False
    try:
        when = datetime.fromisoformat(acknowledged_at)
    except ValueError:
        return False
    age_days = (datetime.now(timezone.utc) - when).total_seconds() / 86400.0
    return age_days < 365  # re-acknowledge yearly


def gate_etsy_opt_in(
    etsy_enabled: bool,
    compliance_path: Path | None = None,
) -> tuple[bool, str | None]:
    """Decide whether the Etsy tier is allowed to run.

    Returns ``(allowed, error_message_or_none)``. When ``etsy_enabled`` is
    False the gate passes immediately with the default non-Etsy behavior. When
    it is True the compliance file must exist and be valid; otherwise the
    microservice refuses to start.
    """
    if not etsy_enabled:
        return True, None
    if not is_acknowledgment_valid(compliance_path):
        return False, (
            "FIRECRAWL_ALLOW_ETSY=true but no valid Etsy risk acknowledgment. "
            "Run `uv run flask --app services/trend-scout:create_app "
            "acknowledge-etsy-risk --note '...'` first."
        )
    return True, None
