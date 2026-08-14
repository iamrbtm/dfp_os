from __future__ import annotations

from app.sources._base import RateLimiter, ScoutResult, random_user_agent, request_with_retry

# These import paths intentionally point at the in-package modules so the
# fetcher pipeline (services/trend-scout/app/services/fetcher_pipeline.py)
# can `from app.sources import fetch_*` consistently.
from app.sources.bgg import fetch_hot_items as fetch_bgg
from app.sources.etsy import fetch_trending as fetch_etsy
from app.sources.google_trends import fetch_trending as fetch_google_trends
from app.sources.internal_demand import fetch_internal_demand
from app.sources.last30days import fetch_trending as fetch_last30days
from app.sources.makerworld import fetch_trending as fetch_makerworld
from app.sources.myminifactory import fetch_trending as fetch_myminifactory
from app.sources.pinterest import fetch_trending as fetch_pinterest
from app.sources.printables import fetch_trending as fetch_printables
from app.sources.reddit import fetch_trending as fetch_reddit
from app.sources.tiktok import fetch_trending as fetch_tiktok

__all__ = [
    "RateLimiter",
    "ScoutResult",
    "random_user_agent",
    "request_with_retry",
    "fetch_internal_demand",
    "fetch_google_trends",
    "fetch_myminifactory",
    "fetch_etsy",
    "fetch_bgg",
    "fetch_makerworld",
    "fetch_printables",
    "fetch_reddit",
    "fetch_pinterest",
    "fetch_tiktok",
    "fetch_last30days",
]
