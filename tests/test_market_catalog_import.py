from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.services import market_catalog_import
from app.services.market_catalog_import import (
    _extract_market_from_text,
    _extract_url,
    _html_to_readable_text,
    _parse_ai_json,
)


def test_market_catalog_import_extracts_url_from_text():
    assert _extract_url("Check https://example.com/market.") == "https://example.com/market"


def test_market_catalog_import_parses_json_fenced_response():
    payload = _parse_ai_json('```json\n{"name": "Test Market"}\n```')

    assert payload == {"name": "Test Market"}


def test_market_catalog_import_non_json_error_is_readable():
    with pytest.raises(ValueError, match="AI provider returned non-JSON output"):
        _parse_ai_json("I cannot browse that URL.")


def test_market_catalog_import_strips_noisy_html():
    text = _html_to_readable_text(
        "<html><style>.x{}</style><script>alert(1)</script><h1>Market</h1><p>Booths $35</p></html>"
    )

    assert "Market" in text
    assert "Booths $35" in text
    assert "alert" not in text


def test_market_catalog_import_fast_path_extracts_clarksville_market():
    payload = _extract_market_from_text(
        url="https://clarksvillechristmasmarket.com/",
        source_text="""
Fetched source URL: https://clarksvillechristmasmarket.com/
Content-Type: text/html; charset=UTF-8

Clarksville Christmas Market – Kick off the holidays in Clarksville, TN with us
Vendor Applications
Save the date we are coming back in 2025!!!!
Apply to be considered as a Vendor below. We will start a rolling acceptance of vendors from here on out.
Venue Information
Venue is a covered pavilion that will have lighting with a compacted dirt floor.
FREE parking also available onsite.
This is an outdoor event.
What to Expect
A family friendly event to help kick off your holidays season. With over 120 local vendors.
Location
1921 Rossview Road
Clarksville, TN 37043
Hours
Friday November 28 2 – 6 pm
Saturday November 29 10 am – 3 pm
Contact
ClarksvilleChristmasMarket@gmail.com
""",
    )

    assert payload is not None
    assert payload["name"] == "Clarksville Christmas Market"
    assert payload["location"]["address"] == "1921 Rossview Road"
    assert payload["location"]["city"] == "Clarksville"
    assert payload["timing"]["anchor_date"] == "2025-11-28"
    assert payload["scale"]["estimated_vendor_count"] == 120
    assert payload["organizer"]["email"] == "ClarksvilleChristmasMarket@gmail.com"
    assert payload["category_hint"] == "holiday_market"


def test_market_catalog_import_sends_fetched_url_context(monkeypatch):
    captured = {}

    class FakeFetchedResponse:
        headers = {"content-type": "text/html"}
        text = "<html><h1>River Market</h1><p>Vendor booths are $35.</p></html>"

        def raise_for_status(self):
            return None

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["request_kwargs"] = kwargs
        return FakeFetchedResponse()

    class FakeCompletions:
        def create(self, **kwargs):
            captured["ai_kwargs"] = kwargs
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=json.dumps({"name": "River Market"}))
                    )
                ]
            )

    class FakeClient:
        chat = SimpleNamespace(completions=FakeCompletions())

        def with_options(self, **kwargs):
            captured["client_options"] = kwargs
            return self

    fake_client = FakeClient()
    monkeypatch.setattr(market_catalog_import.requests, "get", fake_get)
    monkeypatch.setattr(market_catalog_import, "get_openai_compatible_client", lambda: fake_client)
    monkeypatch.setattr(market_catalog_import, "model_for", lambda _key: "test-model")

    payload = market_catalog_import.generate_market_catalog_extraction(
        user_input="https://example.com/river-market", uploaded_file=None
    )

    assert payload == {"name": "River Market"}
    assert captured["url"] == "https://example.com/river-market"
    assert captured["request_kwargs"]["timeout"] == 12
    assert captured["client_options"]["timeout"] == 60
    message_content = captured["ai_kwargs"]["messages"][0]["content"]
    assert any("Fetched source URL" in part["text"] for part in message_content)
    assert any("Vendor booths are $35" in part["text"] for part in message_content)
