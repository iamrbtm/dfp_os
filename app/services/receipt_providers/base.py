from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderResult:
    success: bool
    data: dict[str, Any] | None = None
    raw_text: str | None = None
    raw_json: str | None = None
    confidence: float | None = None
    errors: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


class BaseReceiptProvider:
    name: str = "base"

    def process(self, file_path: str, **kwargs) -> ProviderResult:
        raise NotImplementedError
