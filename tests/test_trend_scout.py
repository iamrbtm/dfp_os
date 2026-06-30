from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models import Category, Product, ProductStatus, ProductType, TrendReport, TrendSnapshot
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
        self._products: list = []

    def query(self, model):
        from app.models import Product
        if model is TrendSnapshot:
            return FakeQuery(self._rows)
        if model is Product:
            return FakeQuery(self._products)
        raise AssertionError(f"Unexpected model: {model}")


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


# ── Phase 1: Fuzzy matching tests ──────────────────────────────────────────

def test_trend_match_normalize_product_term():
    from app.services.trend_match import normalize_product_term
    assert normalize_product_term("3D Printed Dragon") == "dragon"
    assert normalize_product_term("Custom Teacher Keychain") == "teacher keychain"
    assert normalize_product_term("Personalized Name Tag") == "name tag"
    assert normalize_product_term("Printable Fidget Toy") == "fidget toy"


def test_trend_match_find_synonyms():
    from app.services.trend_match import find_synonyms
    syns = find_synonyms("keychain")
    assert "key chain" in syns
    syns2 = find_synonyms("desk sign")
    assert "nameplate" in syns2


def test_trend_match_fuzzy_keywords():
    from app.services.trend_match import fuzzy_match_keywords
    assert fuzzy_match_keywords("dragon", "articulated dragon")
    assert fuzzy_match_keywords("fidget", "fidget slider")
    assert fuzzy_match_keywords("keychain", "custom keychain")
    assert not fuzzy_match_keywords("dragon", "turtle", threshold=0.9)


def test_trend_match_match_product_to_term():
    from app.services.trend_match import match_product_to_term, MatchConfidence
    from app.models.catalog import Product, Category

    cat = Category(name="Dragons")
    product = Product(
        name="Rainbow Dragon",
        category=cat,
        tags="dragon, articulated, rainbow",
    )

    matches, confidence = match_product_to_term("dragon", product)
    assert matches
    assert confidence in (MatchConfidence.EXACT, MatchConfidence.FUZZY)

    matches2, confidence2 = match_product_to_term("fidget", product)
    assert not matches2


def test_trend_match_synonym_matches_potential_product():
    from app.services.trend_match import match_product_to_term
    from app.models.catalog import Product, Category

    cat = Category(name="Keychains")
    product = Product(
        name="Custom Name Keychain",
        category=cat,
        tags="keychain, personalized, name",
    )

    matches, _ = match_product_to_term("name tag", product)
    assert matches


# ── Phase 3: Persistence tests ─────────────────────────────────────────────

def test_opportunity_score_model_creation():
    from app.models.trend import TrendOpportunityScore, TrendReport
    from datetime import datetime, timezone

    report = TrendReport(report_date=datetime.now(timezone.utc))
    score = TrendOpportunityScore(
        report=report,
        candidate_type="current_product",
        product_id=1,
        keyword="test product",
        title="Test Product",
        opportunity_score=75,
        purchase_intent=60,
        trend_velocity=50,
        price_resilience=70,
        low_saturation=65,
        local_fit=40,
        production_fit=80,
        license_risk=10,
        action="print_now",
        inventory_available=5,
        base_price=15.00,
        license_status="commercial_allowed",
        rank=1,
        sources=["catalog", "internal_demand"],
        score_breakdown={"purchase_intent": {"explanation": "test"}},
        match_confidence="exact",
    )
    assert score.opportunity_score == 75
    assert score.action == "print_now"
    assert score.match_confidence == "exact"
    assert score.candidate_type == "current_product"


def test_source_health_model_creation():
    from app.models.trend import SourceHealthRecord
    record = SourceHealthRecord(
        report_id=1,
        source="google_trends",
        status="error",
        keyword="dragon",
        item_count=0,
        error_message="API key not configured",
    )
    assert record.source == "google_trends"
    assert record.status == "error"
    assert record.error_message == "API key not configured"


def test_trend_scout_index_renders_legacy_opportunity_payload(client, login_admin):
    report = TrendReport(
        report_date=datetime.now(timezone.utc),
        summary="Legacy report",
        top_opportunities=[
            {
                "rank": 1,
                "keyword": "dragon",
                "title": "Dragon",
                "score": 42,
                "sources": ["legacy"],
            }
        ],
        growing_categories=[],
        declining_trends=[],
        pipeline_meta={},
    )
    db.session.add(report)
    db.session.commit()

    response = client.get("/admin/trend-scout/")

    assert response.status_code == 200
    assert b"Dragon" in response.data
    assert b"42" in response.data


def test_product_studio_trend_score_uses_existing_user_name(client, login_admin):
    category = Category(name="Trend Score Products", slug="trend-score-products")
    product = Product(
        name="Trend Score Dragon",
        slug="trend-score-dragon",
        category=category,
        product_type=ProductType.FINISHED_GOOD,
        status=ProductStatus.ACTIVE,
        base_price=12,
    )
    db.session.add_all([category, product])
    db.session.commit()

    response = client.get(f"/products/studio/{product.id}/trend-score")

    assert response.status_code == 200
    assert response.get_json()["success"] is True


# ── Phase 2: Score breakdown tests ─────────────────────────────────────────

def test_score_breakdown_includes_raw_inputs():
    candidate = OpportunityCandidate(
        keyword="test dragon",
        title="Test Dragon",
        current_product=True,
        sources={"catalog", "etsy"},
        purchase_raw=150.0,
        velocity_raw=25.0,
        units_sold=10,
        revenue=200.0,
        base_price=20.0,
        estimated_profit=8.0,
        estimated_print_minutes=45,
        license_status="commercial_allowed",
        is_public=True,
        is_pos_visible=True,
    )
    candidate.prices.append(20.0)

    scored = _score_candidate(candidate)
    breakdown = scored.get("score_breakdown", {})

    assert "purchase_intent" in breakdown
    assert breakdown["purchase_intent"]["units_sold"] == 10
    assert breakdown["purchase_intent"]["revenue"] == 200.0

    assert "price_resilience" in breakdown
    assert breakdown["price_resilience"]["base_price"] == 20.0

    assert "local_fit" in breakdown
    assert "matched_terms" in breakdown["local_fit"]

    assert "license_risk" in breakdown
    assert breakdown["license_risk"]["license_status"] == "commercial_allowed"


def test_score_breakdown_matched_risk_terms():
    from app.services.ai.trend_scout.analyzer.trend_detector import _find_matched_risk_terms

    terms = _find_matched_risk_terms("pokemon dragon toy")
    assert "pokemon" in terms

    terms2 = _find_matched_risk_terms("rainbow dragon")
    assert len(terms2) == 0


def test_score_breakdown_matched_local_terms():
    from app.services.ai.trend_scout.analyzer.trend_detector import _find_matched_local_terms

    terms = _find_matched_local_terms("Clarksville TN custom gift")
    assert "clarksville" in terms or "tn" in terms


# ── Phase 7: Source health tests ───────────────────────────────────────────

def test_source_health_from_results():
    from app.services.ai.trend_scout import _source_health_from_results

    results = [
        {
            "source": "etsy",
            "keyword_or_category": "dragon",
            "scraped_at": "2026-06-29T12:00:00+00:00",
            "items": [{"title": "Dragon"}],
            "errors": [],
            "metadata": {"item_count": 1},
        },
        {
            "source": "google_trends",
            "keyword_or_category": "not_configured",
            "scraped_at": "2026-06-29T12:00:00+00:00",
            "items": [],
            "errors": ["SERPAPI_API_KEY not set"],
            "metadata": {"item_count": 0},
        },
    ]

    health = _source_health_from_results(results)
    assert len(health) == 2

    etsy_health = next(h for h in health if h["source"] == "etsy")
    assert etsy_health["status"] == "success"
    assert etsy_health["item_count"] == 1

    google_health = next(h for h in health if h["source"] == "google_trends")
    assert google_health["status"] == "error"
    assert "SERPAPI_API_KEY" in google_health["error_message"]


# ── Score breakdown formatting in product-studio endpoint ──────────────────

def test_score_breakdown_includes_match_confidence():
    candidate = OpportunityCandidate(
        keyword="dragon",
        title="Rainbow Dragon",
        current_product=True,
        sources={"catalog", "etsy"},
        purchase_raw=100.0,
        units_sold=5,
        revenue=75.0,
        base_price=15.0,
        estimated_profit=6.0,
        estimated_print_minutes=60,
        license_status="commercial_allowed",
        is_public=True,
        is_pos_visible=True,
        match_confidence="exact",
    )
    candidate.prices.append(15.0)

    scored = _score_candidate(candidate)
    assert scored.get("match_confidence") == "exact"


def test_opportunity_candidate_phase6_fields_present():
    candidate = OpportunityCandidate(
        keyword="test dragon",
        title="Test Dragon",
        current_product=True,
        product_id=1,
        purchase_raw=50.0,
        units_sold=10,
        revenue=150.0,
        base_price=15.0,
        estimated_profit=6.0,
        inventory_available=5,
        sell_through_rate=0.6667,
        days_since_last_sale=30,
        inventory_age_days=120,
        stockout_detected=False,
        margin_pct=0.4,
        last_sale_at="2026-05-30T14:00:00+00:00",
    )
    assert candidate.sell_through_rate == 0.6667
    assert candidate.days_since_last_sale == 30
    assert candidate.inventory_age_days == 120
    assert candidate.stockout_detected is False
    assert candidate.margin_pct == 0.4
    assert candidate.last_sale_at == "2026-05-30T14:00:00+00:00"


def test_score_candidate_phase6_output_fields():
    candidate = OpportunityCandidate(
        keyword="rainbow dragon",
        title="Rainbow Dragon",
        current_product=True,
        product_id=1,
        sources={"catalog", "etsy"},
        purchase_raw=200.0,
        units_sold=20,
        revenue=300.0,
        base_price=25.0,
        estimated_profit=10.0,
        estimated_print_minutes=120,
        inventory_available=0,
        reorder_target=5,
        license_status="commercial_allowed",
        is_public=True,
        is_pos_visible=True,
        sell_through_rate=1.0,
        days_since_last_sale=5,
        inventory_age_days=200,
        stockout_detected=True,
        margin_pct=0.4,
        last_sale_at="2026-06-24T14:00:00+00:00",
        match_confidence="exact",
    )
    candidate.prices.append(25.0)
    scored = _score_candidate(candidate)
    assert scored.get("sell_through_rate") == 1.0
    assert scored.get("days_since_last_sale") == 5
    assert scored.get("inventory_age_days") == 200
    assert scored.get("stockout_detected") is True
    assert scored.get("margin_pct") == 0.4
    assert scored.get("last_sale_at") == "2026-06-24T14:00:00+00:00"


def test_stockout_boosts_production_fit():
    candidate = OpportunityCandidate(
        keyword="fidget slider",
        title="Fidget Slider",
        current_product=True,
        product_id=2,
        purchase_raw=80.0,
        units_sold=8,
        revenue=120.0,
        base_price=12.0,
        estimated_profit=5.0,
        estimated_print_minutes=45,
        inventory_available=0,
        stockout_detected=True,
    )
    candidate.prices.append(12.0)
    scored = _score_candidate(candidate)
    break_down = scored.get("score_breakdown", {})
    prod_fit = break_down.get("production_fit", {})
    assert prod_fit.get("stockout_detected") is True


def test_stockout_recommends_print_now():
    from app.services.ai.trend_scout.analyzer.trend_detector import _recommend_action

    candidate = OpportunityCandidate(
        keyword="dragon",
        current_product=True,
        product_id=3,
        purchase_raw=60.0,
        units_sold=6,
        inventory_available=0,
        stockout_detected=True,
    )
    scores = {"purchase_intent": 55, "trend_velocity": 30, "opportunity_score": 60, "license_risk": 10}
    action = _recommend_action(candidate, scores)
    assert action == "print_now"


def test_sell_through_low_inventory_clearance():
    from app.services.ai.trend_scout.analyzer.trend_detector import _recommend_action

    candidate = OpportunityCandidate(
        keyword="slow seller",
        current_product=True,
        product_id=4,
        purchase_raw=5.0,
        units_sold=1,
        inventory_available=50,
        sell_through_rate=0.02,
    )
    scores = {"purchase_intent": 20, "trend_velocity": 5, "opportunity_score": 30, "license_risk": 5}
    action = _recommend_action(candidate, scores)
    assert action == "clearance_candidate"


def test_days_since_last_sale_high_retire():
    from app.services.ai.trend_scout.analyzer.trend_detector import _recommend_action

    candidate = OpportunityCandidate(
        keyword="retired product",
        current_product=True,
        product_id=5,
        purchase_raw=0,
        units_sold=0,
        inventory_available=0,
        days_since_last_sale=200,
    )
    scores = {"purchase_intent": 5, "trend_velocity": 5, "opportunity_score": 15, "license_risk": 5}
    action = _recommend_action(candidate, scores)
    assert action == "retire_review"


def test_score_breakdown_includes_margin_pct():
    candidate = OpportunityCandidate(
        keyword="margin item",
        current_product=True,
        product_id=6,
        purchase_raw=30.0,
        units_sold=3,
        revenue=60.0,
        base_price=20.0,
        estimated_profit=10.0,
        margin_pct=0.5,
    )
    candidate.prices.append(20.0)
    scored = _score_candidate(candidate)
    breakdown = scored.get("score_breakdown", {})
    price_break = breakdown.get("price_resilience", {})
    assert price_break.get("margin_pct") == 0.5
