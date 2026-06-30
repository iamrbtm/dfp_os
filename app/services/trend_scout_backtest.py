from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.order import Order, OrderItem
from app.models.pos import PosSale, PosSaleItem
from app.models.trend import TrendOpportunityScore, TrendReport
from app.services.trend_scout_weights import (
    load_score_weights as _load_score_weights,
)


def run_backtest(
    db_session: Session,
    lookback_reports: int = 12,
    sales_window_days: int = 60,
) -> dict[str, Any]:
    reports = (
        db_session.query(TrendReport)
        .order_by(TrendReport.report_date.desc())
        .limit(lookback_reports)
        .all()
    )
    reports.reverse()

    if not reports:
        return {
            "status": "no_data",
            "message": "No TrendReport records found. Run a pipeline first.",
            "report_count": 0,
            "sales_window_days": sales_window_days,
        }

    all_scores: list[dict[str, Any]] = []
    predictions: list[dict[str, Any]] = []

    for report in reports:
        scores = (
            db_session.query(TrendOpportunityScore)
            .filter(
                TrendOpportunityScore.report_id == report.id,
                TrendOpportunityScore.product_id.isnot(None),
            )
            .all()
        )
        for score in scores:
            actual = _measure_actual_sales(db_session, score.product_id, report.report_date, sales_window_days)
            entry = {
                "report_id": report.id,
                "report_date": report.report_date.isoformat(),
                "product_id": score.product_id,
                "keyword": score.keyword,
                "title": score.title,
                "rank": score.rank,
                "action": score.action,
                "opportunity_score": score.opportunity_score,
                "purchase_intent": score.purchase_intent,
                "trend_velocity": score.trend_velocity,
                "price_resilience": score.price_resilience,
                "low_saturation": score.low_saturation,
                "local_fit": score.local_fit,
                "production_fit": score.production_fit,
                "license_risk": score.license_risk,
                "inventory_available": score.inventory_available,
                "base_price": float(score.base_price) if score.base_price else 0.0,
                "actual_quantity_sold": actual["quantity"],
                "actual_revenue": float(actual["revenue"]),
                "actual_order_count": actual["order_count"],
            }
            all_scores.append(entry)
            predictions.append({
                "predicted_score": score.opportunity_score,
                "actual_quantity": actual["quantity"],
                "product_id": score.product_id,
                "keyword": score.keyword,
            })

    if not all_scores:
        return {
            "status": "no_product_scores",
            "message": "No product-linked scores found in the scanned reports.",
            "report_count": len(reports),
            "sales_window_days": sales_window_days,
        }

    stats = _compute_prediction_stats(predictions)
    component_analysis = _analyze_components(all_scores)
    top_k_analysis = _analyze_top_k(all_scores)
    action_analysis = _analyze_action_recommendations(all_scores)
    current_weights = _load_score_weights()
    tuning_hints = _generate_tuning_hints(component_analysis, current_weights)

    return {
        "status": "ok",
        "report_count": len(reports),
        "score_count": len(all_scores),
        "sales_window_days": sales_window_days,
        "predictions": predictions[:500],
        "stats": stats,
        "component_analysis": component_analysis,
        "top_k_analysis": top_k_analysis,
        "action_analysis": action_analysis,
        "current_weights": current_weights,
        "tuning_hints": tuning_hints,
    }


def _measure_actual_sales(
    db_session: Session,
    product_id: int | None,
    after_date: datetime,
    window_days: int,
) -> dict[str, Any]:
    if product_id is None:
        return {"quantity": 0, "revenue": 0.0, "order_count": 0}

    end_date = after_date + __import__("datetime").timedelta(days=window_days)

    order_qty = (
        db_session.query(func.coalesce(func.sum(OrderItem.quantity), 0))
        .join(Order)
        .filter(
            OrderItem.product_id == product_id,
            Order.created_at >= after_date,
            Order.created_at <= end_date,
        )
        .scalar()
        or 0
    )

    order_rev = (
        db_session.query(func.coalesce(func.sum(OrderItem.line_total), 0))
        .join(Order)
        .filter(
            OrderItem.product_id == product_id,
            Order.created_at >= after_date,
            Order.created_at <= end_date,
        )
        .scalar()
        or 0.0
    )

    order_count = (
        db_session.query(func.count(func.distinct(Order.id)))
        .join(OrderItem)
        .filter(
            OrderItem.product_id == product_id,
            Order.created_at >= after_date,
            Order.created_at <= end_date,
        )
        .scalar()
        or 0
    )

    pos_qty = (
        db_session.query(func.coalesce(func.sum(PosSaleItem.quantity), 0))
        .join(PosSale)
        .filter(
            PosSaleItem.product_id == product_id,
            PosSale.created_at >= after_date,
            PosSale.created_at <= end_date,
        )
        .scalar()
        or 0
    )

    pos_rev = (
        db_session.query(func.coalesce(func.sum(PosSaleItem.line_total), 0))
        .join(PosSale)
        .filter(
            PosSaleItem.product_id == product_id,
            PosSale.created_at >= after_date,
            PosSale.created_at <= end_date,
        )
        .scalar()
        or 0.0
    )

    return {
        "quantity": int(order_qty) + int(pos_qty),
        "revenue": float(order_rev) + float(pos_rev),
        "order_count": int(order_count),
    }


def _compute_prediction_stats(predictions: list[dict[str, Any]]) -> dict[str, Any]:
    if not predictions:
        return {}

    max_qty = max(p["actual_quantity"] for p in predictions) or 1
    normalized_actuals = [p["actual_quantity"] / max_qty * 100 for p in predictions]
    predicted_scores = [p["predicted_score"] for p in predictions]

    mae = sum(abs(pa - ps) for pa, ps in zip(normalized_actuals, predicted_scores)) / len(predictions)
    mse = sum((pa - ps) ** 2 for pa, ps in zip(normalized_actuals, predicted_scores)) / len(predictions)
    rmse = math.sqrt(mse)

    high_scorers = [p for p in predictions if p["predicted_score"] >= 60]
    high_sellers = [p for p in high_scorers if p["actual_quantity"] > 0]
    precision_high = len(high_sellers) / len(high_scorers) if high_scorers else 0

    actual_sellers = [p for p in predictions if p["actual_quantity"] > 0]
    predicted_high_among_actual = [p for p in actual_sellers if p["predicted_score"] >= 60]
    recall = len(predicted_high_among_actual) / len(actual_sellers) if actual_sellers else 0

    total_sold = sum(p["actual_quantity"] for p in predictions)
    zero_sellers = sum(1 for p in predictions if p["actual_quantity"] == 0)
    zero_seller_rate = zero_sellers / len(predictions) if predictions else 0

    return {
        "count": len(predictions),
        "mae": round(mae, 2),
        "rmse": round(rmse, 2),
        "precision_at_high_score": round(precision_high, 4),
        "recall_of_sellers": round(recall, 4),
        "f1": round(2 * precision_high * recall / (precision_high + recall + 0.0001), 4),
        "total_units_sold": total_sold,
        "zero_seller_count": zero_sellers,
        "zero_seller_rate": round(zero_seller_rate, 4),
        "avg_predicted_score": round(sum(p["predicted_score"] for p in predictions) / len(predictions), 2),
        "median_predicted_score": sorted(p["predicted_score"] for p in predictions)[len(predictions) // 2],
        "max_predicted_score": max(p["predicted_score"] for p in predictions),
        "min_predicted_score": min(p["predicted_score"] for p in predictions),
    }


def _analyze_components(scores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not scores:
        return []

    max_qty = max(s["actual_quantity_sold"] for s in scores) or 1
    results = []
    components = [
        "opportunity_score",
        "purchase_intent",
        "trend_velocity",
        "price_resilience",
        "low_saturation",
        "local_fit",
        "production_fit",
        "license_risk",
    ]

    for comp in components:
        scores_sorted = sorted(scores, key=lambda s: s.get(comp, 0), reverse=True)
        top_half = scores_sorted[: len(scores_sorted) // 2]
        bottom_half = scores_sorted[len(scores_sorted) // 2 :]

        top_avg_sales = sum(s["actual_quantity_sold"] for s in top_half) / len(top_half) if top_half else 0
        bottom_avg_sales = sum(s["actual_quantity_sold"] for s in bottom_half) / len(bottom_half) if bottom_half else 0

        predictive_ratio = top_avg_sales / (bottom_avg_sales + 0.001)
        values = [s.get(comp, 0) for s in scores]
        actuals = [s["actual_quantity_sold"] / max_qty * 100 for s in scores]

        correlation = _pearson(values, actuals)

        results.append({
            "component": comp,
            "correlation": round(correlation, 4),
            "predictive_ratio": round(predictive_ratio, 2),
            "top_half_avg_sales": round(top_avg_sales, 2),
            "bottom_half_avg_sales": round(bottom_avg_sales, 2),
            "avg_value": round(sum(values) / len(values), 2),
        })

    results.sort(key=lambda r: abs(r["correlation"]), reverse=True)
    return results


def _analyze_top_k(scores: list[dict[str, Any]]) -> dict[str, Any]:
    if not scores:
        return {}

    scored = sorted(scores, key=lambda s: s["opportunity_score"], reverse=True)
    by_actual = sorted(scores, key=lambda s: s["actual_quantity_sold"], reverse=True)

    results = {}
    for k in [5, 10, 15, 20]:
        top_pred = {s["product_id"] for s in scored[:k]}
        top_actual = {s["product_id"] for s in by_actual[:k]}
        overlap = top_pred & top_actual
        precision_k = len(overlap) / k
        results[f"precision_at_{k}"] = round(precision_k, 4)

    return results


def _analyze_action_recommendations(scores: list[dict[str, Any]]) -> dict[str, Any]:
    action_groups: dict[str, list[int]] = {}
    for s in scores:
        act = s.get("action", "unknown")
        if act not in action_groups:
            action_groups[act] = []
        action_groups[act].append(s["actual_quantity_sold"])

    analysis = {}
    for action, qtys in action_groups.items():
        avg_sales = sum(qtys) / len(qtys) if qtys else 0
        zero_count = sum(1 for q in qtys if q == 0)
        analysis[action] = {
            "count": len(qtys),
            "avg_actual_sales": round(avg_sales, 2),
            "zero_sales_count": zero_count,
            "zero_sales_rate": round(zero_count / len(qtys), 4) if qtys else 0,
        }
    return analysis


def _generate_tuning_hints(
    component_analysis: list[dict[str, Any]],
    current_weights: dict[str, float],
) -> list[dict[str, str]]:
    hints = []
    for comp in component_analysis:
        cname = comp["component"]
        correlation = comp["correlation"]
        predictive_ratio = comp["predictive_ratio"]

        if cname == "license_risk":
            if correlation > 0.1:
                hints.append({
                    "component": cname,
                    "hint": (
                        "license_risk has a positive correlation with sales, "
                        "meaning it may not be correctly penalizing risky products. "
                        "Consider reducing the weight."
                    ),
                })
            continue

        if cname == "opportunity_score":
            if correlation < 0.1:
                hints.append({
                    "component": cname,
                    "hint": (
                        "Overall opportunity_score has weak correlation with actual sales. "
                        "Individual component weights may need adjustment."
                    ),
                })
            continue

        weight_key = cname
        current_w = current_weights.get(weight_key, 0)

        if correlation < -0.1:
            hints.append({
                "component": cname,
                "hint": (
                    f"{cname} has a negative correlation ({correlation}) with sales. "
                    f"Current weight is {current_w}. Consider reducing or zeroing this component."
                ),
            })
        elif 0.1 <= correlation < 0.3 and predictive_ratio < 1.5:
            hints.append({
                "component": cname,
                "hint": (
                    f"{cname} has weak predictive power (correlation={correlation}, "
                    f"predictive_ratio={predictive_ratio}). "
                    f"Consider increasing weight if business logic supports it."
                ),
            })
        elif correlation >= 0.3 and predictive_ratio >= 2.0:
            hints.append({
                "component": cname,
                "hint": (
                    f"{cname} has strong predictive power (correlation={correlation}, "
                    f"predictive_ratio={predictive_ratio}). "
                    f"Current weight is {current_w}. Consider holding or slightly increasing."
                ),
            })

    return hints


def _pearson(x: list[float], y: list[float]) -> float:
    n = len(x)
    if n < 3:
        return 0.0
    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(a * b for a, b in zip(x, y))
    sum_x2 = sum(a * a for a in x)
    sum_y2 = sum(b * b for b in y)
    denom = math.sqrt((n * sum_x2 - sum_x * sum_x) * (n * sum_y2 - sum_y * sum_y))
    if denom == 0:
        return 0.0
    return (n * sum_xy - sum_x * sum_y) / denom
