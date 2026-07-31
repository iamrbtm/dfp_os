from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class SliceRequest(BaseModel):
    model_file: str
    profile_name: str | None = None
    center: str | None = "128,128"
    slicer_options: dict[str, Any] | None = None
    preserve_orientation: bool | None = None


class SlicerStats(BaseModel):
    success: bool = False
    error: str | None = None
    filament_grams: Decimal = Decimal("0")
    print_minutes: Decimal = Decimal("0")
    profile_used: str = ""
    stats: dict[str, Any] = Field(default_factory=dict)
    gcode: str | None = None


class SliceResponse(BaseModel):
    success: bool = False
    error: str | None = None
    filament_grams: Decimal = Decimal("0")
    print_minutes: Decimal = Decimal("0")
    profile_used: str = ""
    stats: dict[str, Any] = Field(default_factory=dict)
    gcode: str | None = None
