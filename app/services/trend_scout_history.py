from __future__ import annotations

from typing import Any


from app.extensions import db
from app.models.trend import TrendOpportunityScore, TrendReport


def get_score_history(
    keyword: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    query = (
        db.session.query(
            TrendOpportunityScore.keyword,
            TrendOpportunityScore.opportunity_score,
            TrendOpportunityScore.purchase_intent,
            TrendOpportunityScore.trend_velocity,
            TrendOpportunityScore.price_resilience,
            TrendOpportunityScore.low_saturation,
            TrendOpportunityScore.local_fit,
            TrendOpportunityScore.production_fit,
            TrendOpportunityScore.license_risk,
            TrendReport.report_date,
            TrendReport.id.label("report_id"),
        )
        .join(TrendReport, TrendOpportunityScore.report_id == TrendReport.id)
    )
    if keyword:
        query = query.filter(TrendOpportunityScore.keyword == keyword)
    query = query.order_by(TrendReport.report_date.asc()).limit(limit)
    rows = query.all()
    return [
        {
            "keyword": r.keyword,
            "opportunity_score": r.opportunity_score,
            "purchase_intent": r.purchase_intent,
            "trend_velocity": r.trend_velocity,
            "price_resilience": r.price_resilience,
            "low_saturation": r.low_saturation,
            "local_fit": r.local_fit,
            "production_fit": r.production_fit,
            "license_risk": r.license_risk,
            "report_date": r.report_date.isoformat() if r.report_date else None,
            "report_id": r.report_id,
        }
        for r in rows
    ]


def get_biggest_movers(
    top_n: int = 10,
) -> list[dict[str, Any]]:
    sub = (
        db.session.query(
            TrendOpportunityScore.keyword,
            TrendOpportunityScore.opportunity_score,
            TrendOpportunityScore.report_id,
            TrendReport.report_date,
        )
        .join(TrendReport, TrendOpportunityScore.report_id == TrendReport.id)
        .order_by(TrendReport.report_date.desc())
        .subquery()
    )

    from sqlalchemy import func

    c1 = sub.c
    current = (
        db.session.query(
            c1.keyword,
            c1.opportunity_score,
            c1.report_date,
        )
        .distinct(c1.keyword)
        .filter(c1.report_date.isnot(None))
        .order_by(c1.keyword, c1.report_date.desc())
        .all()
    )

    current_map: dict[str, tuple[int, str | None]] = {}
    for row in current:
        if row.keyword not in current_map:
            current_map[row.keyword] = (row.opportunity_score, row.report_date)

    previous_scores = (
        db.session.query(
            c1.keyword,
            func.max(c1.opportunity_score).label("prev_score"),
        )
        .filter(c1.report_date.isnot(None))
        .group_by(c1.keyword)
        .all()
    )

    prev_map: dict[str, int] = {}
    for row in previous_scores:
        prev_map[row.keyword] = row.prev_score or 0

    movers = []
    for keyword, (current_score, report_date) in current_map.items():
        prev = prev_map.get(keyword, current_score)
        delta = current_score - prev
        movers.append({
            "keyword": keyword,
            "current_score": current_score,
            "previous_score": prev,
            "delta": delta,
            "report_date": report_date,
        })

    movers.sort(key=lambda m: abs(m["delta"]), reverse=True)
    return movers[:top_n]
