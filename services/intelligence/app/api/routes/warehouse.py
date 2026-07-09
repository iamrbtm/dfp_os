from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.warehouse import (
    ChannelPerformanceSummaryListResponse,
    ProductSalesSummaryListResponse,
    SeasonalProductPerformanceListResponse,
    WarehouseBuildResponse,
)
from app.security import verify_internal_token
from app.services.legacy_warehouse import rebuild_legacy_warehouse
from app.services.warehouse import (
    list_channel_summaries,
    list_product_summaries,
    list_seasonal_summaries,
    rebuild_square_sales_warehouse,
)

router = APIRouter(prefix="/warehouse", tags=["warehouse"], dependencies=[Depends(verify_internal_token)])


@router.post("/rebuild-square", response_model=WarehouseBuildResponse)
async def rebuild_square_warehouse(db: AsyncSession = Depends(get_db)):
    return await rebuild_square_sales_warehouse(db)


@router.post("/rebuild-legacy")
async def rebuild_legacy_warehouse_endpoint(db: AsyncSession = Depends(get_db)):
    return await rebuild_legacy_warehouse(db)


@router.get("/products", response_model=ProductSalesSummaryListResponse)
async def product_summaries(limit: int = Query(default=25, ge=1, le=250), db: AsyncSession = Depends(get_db)):
    return ProductSalesSummaryListResponse(items=await list_product_summaries(db, limit=limit))


@router.get("/channels", response_model=ChannelPerformanceSummaryListResponse)
async def channel_summaries(limit: int = Query(default=25, ge=1, le=250), db: AsyncSession = Depends(get_db)):
    return ChannelPerformanceSummaryListResponse(items=await list_channel_summaries(db, limit=limit))


@router.get("/seasonal-products", response_model=SeasonalProductPerformanceListResponse)
async def seasonal_summaries(
    sale_month: int | None = Query(default=None, ge=1, le=12),
    limit: int = Query(default=25, ge=1, le=250),
    db: AsyncSession = Depends(get_db),
):
    return SeasonalProductPerformanceListResponse(items=await list_seasonal_summaries(db, sale_month=sale_month, limit=limit))
