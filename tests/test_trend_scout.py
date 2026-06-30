from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models import TrendSnapshot
from app.services.ai.trend_scout.analyzer.new_category_discovery import discover_new_categories
from app.services.ai.trend_scout.analyzer.trend_detector import (
    OpportunityCandidate,
    compute_top_opportunities,
    compute_velocity_and_momentum,
    _score_candidate,
)
from app.services.ai.trend_scout.sources.google_trends import fetch_trending as fetch_google_trends
from app.services.ai.trend_scout.sources.tiktok import fetch_trending as fetch_tiktok
from app.services.ai.trend_scout.sources.etsy import fetch_trending as fetch_etsy
from app.services.internal_demand import extract_terms


class FakeQuery:
    def __init__(self, rows: list[TrendSnapshot]):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self._rows


class FakeSession:
    def __init__(self, rows: list[TrendSnapshot]):
        self._rows = rows

    def query(self, model):
        assert model is TrendSnapshot
        return FakeQuery(self._rows)


def _snapshot(
    source: str,
    keyword: str,
    items: list[dict],
    *,
    scraped_at: datetime | None = None,
    errors: list[str] | None = None,
) -> TrendSnapshot:
    when = scraped_at or datetime.now(timezone.utc)
    return TrendSnapshot(
        source=source,
        keyword_or_category=keyword,
        scraped_at=when,
        raw_metadata={
            "source": source,
            "keyword_or_category": keyword,
            "scraped_at": when.isoformat(),
            "items": items,
            "errors": errors or [],
            "metadata": {"item_count": len(items), "has_signal": bool(items)},
        },
    )


def test_top_opportunities_ignore_error_only_snapshots_and_boost_cross_source():
    now = datetime.now(timezone.utc)
    session = FakeSession(
        [
            _snapshot(
                "etsy",
                "not_configured",
                [],
                scraped_at=now,
                errors=["ETSY_API_KEY environment variable not set"],
            ),
            _snapshot(
                "makerworld",
                "3D printed dragon",
                [{"title": "Crystal Dragon", "likes": 120, "downloads": 900}],
                scraped_at=now,
            ),
            _snapshot(
                "etsy",
                "dragon",
                [{"title": "Articulated Dragon", "num_favorers": 50, "views": 800}],
                scraped_at=now,
            ),
            _snapshot(
                "printables",
                "fidget",
                [{"title": "Fidget Slider", "likes": 20}],
                scraped_at=now,
            ),
        ]
    )

    opportunities = compute_top_opportunities(session)

    assert opportunities[0]["keyword"] == "dragon"
    assert opportunities[0]["sources"] == ["etsy", "makerworld"]
    assert all(item["keyword"] != "configured" for item in opportunities)
    for key in (
        "purchase_intent",
        "trend_velocity",
        "price_resilience",
        "low_saturation",
        "local_fit",
        "production_fit",
        "license_risk",
        "action",
    ):
        assert key in opportunities[0]


def test_internal_demand_signal_can_outrank_maker_interest():
    now = datetime.now(timezone.utc)
    session = FakeSession(
        [
            _snapshot(
                "makerworld",
                "dragon",
                [{"title": "Cool Dragon STL", "likes": 300, "downloads": 900}],
                scraped_at=now,
            ),
            _snapshot(
                "internal_demand",
                "buyer_intent",
                [
                    {
                        "title": "Personalized Backpack Name Tag",
                        "keyword": "personalized backpack name tag",
                        "event_count": 4,
                        "quantity": 8,
                        "purchase_score": 64,
                        "revenue": 112,
                    }
                ],
                scraped_at=now,
            ),
        ]
    )

    opportunities = compute_top_opportunities(session)

    assert opportunities[0]["keyword"] == "personalized backpack name tag"
    assert opportunities[0]["sources"] == ["internal_demand"]
    assert opportunities[0]["purchase_intent"] > opportunities[1]["purchase_intent"]


def test_existing_product_matrix_can_recommend_clearance():
    candidate = OpportunityCandidate(
        keyword="slow moving dragon",
        title="Slow Moving Dragon",
        current_product=True,
        inventory_available=12,
        reorder_target=0,
        base_price=12,
        estimated_profit=5,
        estimated_print_minutes=75,
        license_status="commercial_allowed",
        is_public=True,
        is_pos_visible=True,
    )

    scored = _score_candidate(candidate)

    assert scored["candidate_type"] == "current_product"
    assert scored["action"] == "clearance_candidate"
    assert scored["purchase_intent"] < 20


def test_existing_product_matrix_can_recommend_print_now():
    candidate = OpportunityCandidate(
        keyword="custom teacher keychain",
        title="Custom Teacher Keychain",
        current_product=True,
        sources={"catalog", "internal_demand"},
        purchase_raw=180,
        velocity_raw=25,
        inventory_available=0,
        reorder_target=6,
        units_sold=16,
        revenue=240,
        base_price=15,
        estimated_profit=9,
        estimated_print_minutes=35,
        license_status="commercial_allowed",
        is_public=True,
        is_pos_visible=True,
    )

    scored = _score_candidate(candidate)

    assert scored["action"] == "print_now"
    assert scored["opportunity_score"] >= 70
    assert scored["license_risk"] < 20


def test_velocity_normalizes_keywords_and_uses_only_signal_rows():
    now = datetime.now(timezone.utc)
    session = FakeSession(
        [
            _snapshot(
                "printables",
                "3D printed fidget",
                [{"title": "Fidget Spinner", "likes": 5}],
                scraped_at=now - timedelta(days=10),
            ),
            _snapshot(
                "printables",
                "fidget",
                [
                    {"title": "Fidget Slider", "likes": 100, "downloads": 500},
                    {"title": "Fidget Cube", "likes": 50, "downloads": 200},
                ],
                scraped_at=now - timedelta(days=1),
            ),
            _snapshot("printables", "pipeline_error", [], scraped_at=now, errors=["boom"]),
        ]
    )

    trends = compute_velocity_and_momentum(session, lookback_weeks=4)

    assert trends["metadata"]["total_rows"] == 3
    assert trends["metadata"]["signal_rows"] == 2
    assert trends["momentum"]["printables"]["fidget"]["direction"] == "up"


def test_category_discovery_uses_frequency_fallback_without_embeddings():
    now = datetime.now(timezone.utc)
    session = FakeSession(
        [
            _snapshot(
                "bgg",
                "hot_boardgameaccessory",
                [
                    {"title": "Flexi Dragon STL"},
                    {"title": "Flexi Dragon model"},
                    {"title": "Dice Tower STL"},
                ],
                scraped_at=now,
            )
        ]
    )

    result = discover_new_categories(session, api_key="", lookback_days=7)

    phrases = [
        phrase for cluster in result["clusters"] for phrase in cluster.get("top_phrases", [])
    ]
    assert "flexi dragon" in phrases
    assert result["total_clusters_found"] >= 1


def test_internal_demand_extracts_buyer_terms_without_raw_text_storage():
    terms = extract_terms("Can you make a custom teacher gift name keychain for back to school?")

    assert "custom" in terms
    assert "teacher" in terms
    assert "back to school" in terms
    assert "name" in terms


def test_google_trends_source_degrades_without_provider(monkeypatch):
    class NoopLimiter:
        def wait(self):
            return None

    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    results = fetch_google_trends(None, NoopLimiter())

    assert results[0].source == "google_trends"
    assert results[0].keyword_or_category == "not_configured"
    assert results[0].errors


def test_tiktok_source_degrades_without_research_token(monkeypatch):
    class NoopLimiter:
        def wait(self):
            return None

    monkeypatch.delenv("TIKTOK_RESEARCH_ACCESS_TOKEN", raising=False)
    results = fetch_tiktok(None, NoopLimiter())

    assert results[0].source == "tiktok"
    assert results[0].keyword_or_category == "not_configured"
    assert results[0].errors


def test_etsy_price_uses_api_divisor(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "results": [
                    {
                        "listing_id": 123,
                        "title": "Dragon",
                        "url": "https://example.test/listing/123",
                        "price": {"amount": 1299, "divisor": 100, "currency_code": "USD"},
                    }
                ]
            }

    class FakeSession:
        def get(self, *args, **kwargs):
            return FakeResponse()

    class NoopLimiter:
        def wait(self):
            return None

    monkeypatch.setenv("ETSY_API_KEY", "test-key")

    results = fetch_etsy(FakeSession(), NoopLimiter())

    assert results
    assert results[0].items[0]["price"] == 12.99
