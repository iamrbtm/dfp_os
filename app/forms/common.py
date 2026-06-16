from __future__ import annotations

from decimal import Decimal
from enum import Enum

from wtforms import SelectField


def enum_choices(enum_class: type[Enum]) -> list[tuple[str, str]]:
    return [(item.value, item.value.replace("_", " ").title()) for item in enum_class]


def decimal_or_zero(value: Decimal | None) -> Decimal:
    return value if value is not None else Decimal("0")


class OptionalSelectField(SelectField):
    def pre_validate(self, form):
        if self.data in (None, "", 0, "0"):
            return
        super().pre_validate(form)
