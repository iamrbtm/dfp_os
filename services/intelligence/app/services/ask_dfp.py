from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AskDfpRun, ChannelPerformanceSummary, ProductSalesSummary, SeasonalProductPerformance
from app.schemas.knowledge import AskDfpRequest, AskDfpResponse
from app.services.knowledge import search_knowledge

ALLOWED_TOOLS = {"product_summary", "seasonal_summary", "channel_summary", "knowledge_search"}


async def answer_question(db: AsyncSession, payload: AskDfpRequest) -> AskDfpResponse:
    tools = [tool for tool in payload.allowed_tools if tool in ALLOWED_TOOLS]
    evidence: list[dict] = []
    answer_parts: list[str] = []

    if "product_summary" in tools:
        products = (
            await db.execute(
                select(ProductSalesSummary)
                .order_by(ProductSalesSummary.total_units.desc(), ProductSalesSummary.total_net_sales_cents.desc())
                .limit(payload.limit)
            )
        ).scalars().all()
        if products:
            evidence.append(
                {
                    "tool": "product_summary",
                    "items": [
                        {
                            "product_key": item.product_key,
                            "product_name": item.product_name,
                            "total_units": str(item.total_units),
                            "total_net_sales_cents": item.total_net_sales_cents,
                            "avg_units_per_active_month": str(item.avg_units_per_active_month),
                        }
                        for item in products
                    ],
                }
            )
            top = products[0]
            answer_parts.append(
                f"Top historical product signal is {top.product_name} with {top.total_units} units and "
                f"{top.avg_units_per_active_month} average units per active month."
            )

    if "seasonal_summary" in tools:
        seasonal = (
            await db.execute(
                select(SeasonalProductPerformance)
                .order_by(SeasonalProductPerformance.total_units.desc())
                .limit(payload.limit)
            )
        ).scalars().all()
        if seasonal:
            evidence.append(
                {
                    "tool": "seasonal_summary",
                    "items": [
                        {
                            "product_key": item.product_key,
                            "product_name": item.product_name,
                            "sale_month": item.sale_month,
                            "total_units": str(item.total_units),
                        }
                        for item in seasonal
                    ],
                }
            )

    if "channel_summary" in tools:
        channels = (
            await db.execute(
                select(ChannelPerformanceSummary)
                .order_by(ChannelPerformanceSummary.total_net_sales_cents.desc())
                .limit(payload.limit)
            )
        ).scalars().all()
        if channels:
            evidence.append(
                {
                    "tool": "channel_summary",
                    "items": [
                        {
                            "channel_name": item.channel_name,
                            "total_units": str(item.total_units),
                            "total_net_sales_cents": item.total_net_sales_cents,
                        }
                        for item in channels
                    ],
                }
            )
            answer_parts.append(f"Best historical channel by revenue is {channels[0].channel_name}.")

    if "knowledge_search" in tools:
        notes = await search_knowledge(db, payload.question, limit=payload.limit)
        if notes:
            evidence.append({"tool": "knowledge_search", "items": [item.model_dump() for item in notes]})
            answer_parts.append(f"Relevant notes were found in {notes[0].title}.")

    if not answer_parts:
        answer_parts.append("I do not have enough imported warehouse data or notes to answer with evidence yet.")

    run = AskDfpRun(
        question=payload.question,
        answer=" ".join(answer_parts),
        allowed_tools=tools,
        evidence=evidence,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return AskDfpResponse(
        id=run.id,
        question=run.question,
        answer=run.answer,
        allowed_tools=run.allowed_tools,
        evidence=run.evidence,
        created_at=run.created_at,
    )
