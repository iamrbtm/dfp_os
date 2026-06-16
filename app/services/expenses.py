from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, extract

from app.extensions import db
from app.models import Expense


def get_expense_summary() -> dict:
    total = db.session.query(func.sum(Expense.amount)).scalar() or Decimal(0)

    by_category = (
        db.session.query(
            Expense.category,
            func.count(Expense.id).label("count"),
            func.sum(Expense.amount).label("total"),
        )
        .group_by(Expense.category)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )

    monthly_totals = (
        db.session.query(
            extract("year", Expense.date).label("year"),
            extract("month", Expense.date).label("month"),
            func.sum(Expense.amount).label("total"),
        )
        .group_by("year", "month")
        .order_by(extract("year", Expense.date).desc(), extract("month", Expense.date).desc())
        .limit(12)
        .all()
    )

    return {
        "total": total,
        "by_category": [
            {"category": r[0], "count": int(r[1]), "total": Decimal(str(r[2])) if r[2] else Decimal(0)}
            for r in by_category
        ],
        "monthly_totals": [
            {"year": int(r[0]), "month": int(r[1]), "total": Decimal(str(r[2])) if r[2] else Decimal(0)}
            for r in monthly_totals
        ],
    }
