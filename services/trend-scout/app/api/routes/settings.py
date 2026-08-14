from __future__ import annotations

from fastapi import APIRouter, Depends

from app.database import async_session_factory
from app.schemas.api import SettingsSourceToggleRequest, SettingsSourceToggleResponse
from app.security import SCOPE_READ, SCOPE_WRITE, verify_internal_token
from app.services import weights as weights_service

router = APIRouter(
    prefix="/settings",
    tags=["settings"],
    dependencies=[Depends(verify_internal_token)],
)


@router.get("/source-toggles")
async def list_source_toggles(_token: str = SCOPE_READ) -> dict:
    async with async_session_factory() as session:
        state = await weights_service.load_source_enabled_state(
            session, list(weights_service.DEFAULT_SOURCE_WEIGHTS.keys())
        )
    return {"items": [{"source": k, "enabled": v} for k, v in state.items()]}


@router.post("/source-toggles", response_model=SettingsSourceToggleResponse)
async def toggle_source(
    payload: SettingsSourceToggleRequest,
    _token: str = SCOPE_WRITE,
) -> SettingsSourceToggleResponse:
    async with async_session_factory() as session:
        value = 1.0 if payload.enabled else 0.0
        await weights_service.save_weight(
            session,
            group=weights_service.GROUP_SOURCE_ENABLED,
            key=payload.source,
            value=value,
            description="source enabled toggle",
        )
        await session.commit()
    return SettingsSourceToggleResponse(source=payload.source, enabled=payload.enabled)
