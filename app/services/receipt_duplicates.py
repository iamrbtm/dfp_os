from __future__ import annotations

from datetime import timedelta


from app.extensions import db
from app.models import Receipt, ReceiptStatus


DUPLICATE_WEIGHTS = {
    "hash_exact": 50,
    "merchant_match": 20,
    "date_close": 10,
    "total_match": 10,
    "receipt_number_match": 10,
}


def check_duplicates(receipt_id: int) -> dict:
    receipt = db.session.get(Receipt, receipt_id)
    if not receipt:
        return {"score": 0, "possible_duplicates": []}

    candidates = (
        Receipt.query.filter(
            Receipt.id != receipt_id,
            Receipt.deleted_at.is_(None),
            Receipt.status.in_([ReceiptStatus.APPROVED, ReceiptStatus.NEEDS_REVIEW, ReceiptStatus.POSSIBLE_DUPLICATE]),
        )
        .all()
    )

    results = []
    for candidate in candidates:
        score = 0
        reasons = []

        if receipt.file_hash and candidate.file_hash and receipt.file_hash == candidate.file_hash:
            score += DUPLICATE_WEIGHTS["hash_exact"]
            reasons.append("exact file hash match")

        if receipt.merchant_name and candidate.merchant_name and receipt.merchant_name.lower() == candidate.merchant_name.lower():
            score += DUPLICATE_WEIGHTS["merchant_match"]
            reasons.append("merchant name match")

        if receipt.date_time and candidate.date_time:
            diff = abs(receipt.date_time - candidate.date_time)
            if diff <= timedelta(hours=1):
                score += DUPLICATE_WEIGHTS["date_close"]
                reasons.append("date/time within 1 hour")

        if receipt.grand_total and candidate.grand_total and receipt.grand_total == candidate.grand_total:
            score += DUPLICATE_WEIGHTS["total_match"]
            reasons.append("grand total match")

        if receipt.receipt_number and candidate.receipt_number and receipt.receipt_number == candidate.receipt_number:
            score += DUPLICATE_WEIGHTS["receipt_number_match"]
            reasons.append("receipt number match")

        if score > 0:
            results.append({
                "id": candidate.id,
                "score": score,
                "reasons": reasons,
                "merchant_name": candidate.merchant_name,
                "grand_total": candidate.grand_total,
                "date_time": candidate.date_time.isoformat() if candidate.date_time else None,
            })

    results.sort(key=lambda r: r["score"], reverse=True)

    threshold = 50
    is_duplicate = any(r["score"] >= threshold for r in results)

    return {
        "score": max((r["score"] for r in results), default=0),
        "is_duplicate": is_duplicate,
        "possible_duplicates": results,
    }


def resolve_duplicate(receipt_id: int, action: str, duplicate_of_id: int | None = None) -> dict:
    receipt = db.session.get(Receipt, receipt_id)
    if not receipt:
        return {"success": False, "errors": ["Receipt not found."]}

    if action == "keep":
        receipt.status = ReceiptStatus.NEEDS_REVIEW
        receipt.duplicate_group_id = None
    elif action == "reject_duplicate":
        receipt.status = ReceiptStatus.REJECTED
    elif action == "merge":
        receipt.duplicate_group_id = duplicate_of_id
        receipt.status = ReceiptStatus.NEEDS_REVIEW

    db.session.commit()
    return {"success": True}
