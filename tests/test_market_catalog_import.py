from __future__ import annotations

import pytest

from app.services.market_catalog_import import _extract_url, _parse_ai_json


def test_market_catalog_import_extracts_url_from_text():
    assert _extract_url("Check https://example.com/market.") == "https://example.com/market"


def test_market_catalog_import_parses_json_fenced_response():
    payload = _parse_ai_json('```json\n{"name": "Test Market"}\n```')

    assert payload == {"name": "Test Market"}


def test_market_catalog_import_non_json_error_is_readable():
    with pytest.raises(ValueError, match="AI provider returned non-JSON output"):
        _parse_ai_json("I cannot browse that URL.")
