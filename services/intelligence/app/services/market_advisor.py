from __future__ import annotations

from datetime import date
from decimal import ROUND_CEILING, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MarketAdvisorRecommendation, MarketAdvisorRun, ProductSalesSummary, SeasonalProductPerformance
from app.schemas.warehouse import MarketAdvisorRequest, MarketAdvisorRunResponse


def _ceil_decimal(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_CEILING))


def _risk_level(active_months: int, total_units: Decimal, seasonal_units: Decimal) -> str:
    if active_months >= 6 and total_units >= Decimal("25"):
        return "low"
    if seasonal_units > 0 or total_units >= Decimal("10"):
        return "medium"
    return "high"


def _target_month(market_date: date | None) -> int | None:
    return market_date.month if market_date else None


async def generate_market_advisor_run(db: AsyncSession, payload: MarketAdvisorRequest) -> MarketAdvisorRunResponse:
    month = _target_month(payload.market_date)
    summaries = (
        await db.execute(
            select(ProductSalesSummary).order_by(
                ProductSalesSummary.total_units.desc(),
                ProductSalesSummary.total_net_sales_cents.desc(),
            )
        )
    ).scalars().all()

    seasonal_by_product: dict[str, SeasonalProductPerformance] = {}
    if month is not None:
        seasonal_rows = (
            await db.execute(
                select(SeasonalProductPerformance).where(SeasonalProductPerformance.sale_month == month)
            )
        ).scalars().all()
        seasonal_by_product = {row.product_key: row for row in seasonal_rows}

    run = MarketAdvisorRun(
        market_name=payload.market_name,
        market_date=payload.market_date,
        event_type=payload.event_type,
        max_products=payload.max_products,
        input_context=payload.model_dump(mode="json"),
    )
    db.add(run)
    await db.flush()

    scored: list[tuple[Decimal, ProductSalesSummary, SeasonalProductPerformance | None]] = []
    for summary in summaries:
        seasonal = seasonal_by_product.get(summary.product_key)
        seasonal_units = Decimal(seasonal.total_units) if seasonal is not None else Decimal("0")
        velocity = Decimal(summary.avg_units_per_active_month)
        total_units = Decimal(summary.total_units)
        transaction_weight = Decimal(summary.transaction_count) / Decimal("10")
        score = (
            (velocity * Decimal("2.0"))
            + (seasonal_units * Decimal("1.5"))
            + transaction_weight
            + (total_units / Decimal("20"))
        )
        if (
            summary.category_name
            and payload.event_type
            and payload.event_type.casefold() in summary.category_name.casefold()
        ):
            score += Decimal("5.0")
        scored.append((score, summary, seasonal))

    scored.sort(key=lambda item: item[0], reverse=True)
    recommendations: list[MarketAdvisorRecommendation] = []
    for rank, (score, summary, seasonal) in enumerate(scored[: payload.max_products], start=1):
        seasonal_units = Decimal(seasonal.total_units) if seasonal is not None else Decimal("0")
        baseline = max(Decimal(summary.avg_units_per_active_month), seasonal_units)
        if baseline <= 0:
            baseline = Decimal(summary.total_units) / Decimal(max(summary.active_months, 1))
        suggested_quantity = max(_ceil_decimal(baseline * Decimal("1.25")), 1)
        on_hand = max(int(payload.inventory_by_product_key.get(summary.product_key, 0)), 0)
        print_quantity = max(suggested_quantity - on_hand, 0)
        expected_revenue = suggested_quantity * int(summary.avg_net_sales_cents_per_unit or 0)
        risk = _risk_level(int(summary.active_months), Decimal(summary.total_units), seasonal_units)
        rationale = (
            f"Recommend {suggested_quantity} based on {summary.total_units} historical units, "
            f"{summary.avg_units_per_active_month} average units per active month"
        )
        if seasonal is not None:
            rationale += f", and {seasonal.total_units} units sold in month {seasonal.sale_month}"
        rationale += f". Current on-hand is {on_hand}, so print {print_quantity}."
        recommendation = MarketAdvisorRecommendation(
            run_id=run.id,
            rank=rank,
            product_key=summary.product_key,
            product_name=summary.product_name,
            category_name=summary.category_name,
            suggested_quantity=suggested_quantity,
            suggested_print_quantity=print_quantity,
            expected_revenue_cents=expected_revenue,
            risk_level=risk,
            score=score,
            rationale=rationale,
            evidence={
                "product_summary": {
                    "total_units": str(summary.total_units),
                    "total_net_sales_cents": summary.total_net_sales_cents,
                    "transaction_count": summary.transaction_count,
                    "active_months": summary.active_months,
                    "avg_units_per_active_month": str(summary.avg_units_per_active_month),
                    "avg_net_sales_cents_per_unit": summary.avg_net_sales_cents_per_unit,
                    "first_sale_date": summary.first_sale_date.isoformat() if summary.first_sale_date else None,
                    "last_sale_date": summary.last_sale_date.isoformat() if summary.last_sale_date else None,
                },
                "seasonal_summary": {
                    "sale_month": seasonal.sale_month,
                    "total_units": str(seasonal.total_units),
                    "total_net_sales_cents": seasonal.total_net_sales_cents,
                    "transaction_count": seasonal.transaction_count,
                }
                if seasonal is not None
                else None,
                "inventory_on_hand": on_hand,
                "score": str(score),
            },
        )
        db.add(recommendation)
        recommendations.append(recommendation)

    await db.commit()
    await db.refresh(run)
    for recommendation in recommendations:
        await db.refresh(recommendation)
    return MarketAdvisorRunResponse(
        id=run.id,
        market_name=run.market_name,
        market_date=run.market_date,
        event_type=run.event_type,
        max_products=run.max_products,
        status=run.status,
        input_context=run.input_context,
        created_at=run.created_at,
        recommendations=recommendations,
    )
