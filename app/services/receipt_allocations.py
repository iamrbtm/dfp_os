from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.extensions import db
from app.models import (
    Receipt,
    ReceiptLineItem,
    ReceiptLineAllocation,
    ReceiptAdjustmentAllocation,
    AdjustmentType,
    AllocationMethod,
)


def allocate_taxes_and_fees(receipt_id: int) -> dict[str, Any]:
    receipt = db.session.get(Receipt, receipt_id)
    if not receipt:
        return {"success": False, "errors": ["Receipt not found."]}

    items = ReceiptLineItem.query.filter_by(receipt_id=receipt_id).order_by(ReceiptLineItem.row_order).all()
    if not items:
        return {"success": False, "errors": ["No line items found."]}

    receipts_adjustments = ReceiptAdjustmentAllocation.query.filter_by(receipt_id=receipt_id).all()
    existing_by_type = {a.adjustment_type: a for a in receipts_adjustments}

    results = {}

    # 1. Tax allocation
    tax_total = receipt.tax_total or Decimal("0")
    if tax_total > 0 and AdjustmentType.TAX.value not in existing_by_type:
        tax_result = _allocate_tax(items, tax_total, receipt.id)
        results["tax"] = tax_result

    # 2. Fee allocation
    fee_total = receipt.fee_total or Decimal("0")
    if fee_total > 0 and AdjustmentType.FEE.value not in existing_by_type:
        fee_result = _allocate_fees(items, fee_total, receipt.id)
        results["fee"] = fee_result

    # 3. Discount allocation
    discount_total = receipt.discount_total or Decimal("0")
    if discount_total > 0 and AdjustmentType.DISCOUNT.value not in existing_by_type:
        discount_result = _allocate_discount(items, discount_total, receipt.id)
        results["discount"] = discount_result

    # 4. Tip allocation
    tip_total = receipt.tip_total or Decimal("0")
    if tip_total > 0 and AdjustmentType.TIP.value not in existing_by_type:
        tip_result = _allocate_tip(items, tip_total, receipt.id)
        results["tip"] = tip_result

    # 5. Deposit allocation  
    deposit_total = receipt.deposit_total or Decimal("0")
    if deposit_total > 0 and AdjustmentType.DEPOSIT.value not in existing_by_type:
        deposit_result = _allocate_deposit(items, deposit_total, receipt.id)
        results["deposit"] = deposit_result

    db.session.commit()
    return {"success": True, "results": results}


def _allocate_tax(items: list[ReceiptLineItem], tax_total: Decimal, receipt_id: int) -> dict:
    taxable_items = [i for i in items if i.taxable_status == "taxable" and i.line_subtotal]
    total_taxable = sum(i.line_subtotal for i in taxable_items) if taxable_items else Decimal("0")

    if not taxable_items or total_taxable == 0:
        taxable_items = [i for i in items if i.line_subtotal]
        total_taxable = sum(i.line_subtotal for i in taxable_items) if taxable_items else Decimal("0")

    if not taxable_items or total_taxable == 0:
        alloc = ReceiptAdjustmentAllocation(
            receipt_id=receipt_id,
            adjustment_type=AdjustmentType.TAX,
            allocation_method=AllocationMethod.UNALLOCATED,
            source_amount=tax_total,
            allocated_amount=Decimal("0"),
            unallocated_amount=tax_total,
            calculation_json=json.dumps({"reason": "No taxable items found"}),
        )
        db.session.add(alloc)
        return {"method": "unallocated"}

    allocated_total = Decimal("0")
    allocations = []
    for i, item in enumerate(taxable_items):
        if i == len(taxable_items) - 1:
            allocated = tax_total - allocated_total
        else:
            proportion = item.line_subtotal / total_taxable
            allocated = (tax_total * proportion).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        allocated_total += allocated
        item.line_tax = (item.line_tax or Decimal("0")) + allocated
        allocations.append({"item_id": item.id, "amount": str(allocated)})

    alloc = ReceiptAdjustmentAllocation(
        receipt_id=receipt_id,
        adjustment_type=AdjustmentType.TAX,
        allocation_method=AllocationMethod.TAXABLE_PROPORTIONAL,
        source_amount=tax_total,
        allocated_amount=allocated_total,
        unallocated_amount=tax_total - allocated_total,
        calculation_json=json.dumps({"allocations": allocations, "total_allocated": str(allocated_total)}),
    )
    db.session.add(alloc)
    return {"method": "taxable_proportional", "allocated": str(allocated_total)}


def _allocate_fees(items: list[ReceiptLineItem], fee_total: Decimal, receipt_id: int) -> dict:
    return _proportional_allocate(items, fee_total, receipt_id, AdjustmentType.FEE, AllocationMethod.SUBTOTAL_PROPORTIONAL)


def _allocate_discount(items: list[ReceiptLineItem], discount_total: Decimal, receipt_id: int) -> dict:
    return _proportional_allocate(items, discount_total, receipt_id, AdjustmentType.DISCOUNT, AllocationMethod.SUBTOTAL_PROPORTIONAL)


def _allocate_tip(items: list[ReceiptLineItem], tip_total: Decimal, receipt_id: int) -> dict:
    return _proportional_allocate(items, tip_total, receipt_id, AdjustmentType.TIP, AllocationMethod.SUBTOTAL_PROPORTIONAL)


def _allocate_deposit(items: list[ReceiptLineItem], deposit_total: Decimal, receipt_id: int) -> dict:
    return _proportional_allocate(items, deposit_total, receipt_id, AdjustmentType.DEPOSIT, AllocationMethod.SUBTOTAL_PROPORTIONAL)


def _proportional_allocate(items: list, total: Decimal, receipt_id: int, adj_type: AdjustmentType, method: AllocationMethod) -> dict:
    items_with_subtotal = [i for i in items if i.line_subtotal]
    total_subtotal = sum(i.line_subtotal for i in items_with_subtotal) if items_with_subtotal else Decimal("0")

    if not items_with_subtotal or total_subtotal == 0:
        alloc = ReceiptAdjustmentAllocation(
            receipt_id=receipt_id,
            adjustment_type=adj_type,
            allocation_method=AllocationMethod.UNALLOCATED,
            source_amount=total,
            allocated_amount=Decimal("0"),
            unallocated_amount=total,
            calculation_json=json.dumps({"reason": "No items with subtotal found"}),
        )
        db.session.add(alloc)
        return {"method": "unallocated"}

    allocated_total = Decimal("0")
    allocations = []
    for i, item in enumerate(items_with_subtotal):
        if i == len(items_with_subtotal) - 1:
            allocated = total - allocated_total
        else:
            proportion = item.line_subtotal / total_subtotal
            allocated = (total * proportion).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        allocated_total += allocated
        _apply_adjustment_to_item(item, adj_type, allocated)
        allocations.append({"item_id": item.id, "amount": str(allocated)})

    alloc = ReceiptAdjustmentAllocation(
        receipt_id=receipt_id,
        adjustment_type=adj_type,
        allocation_method=method,
        source_amount=total,
        allocated_amount=allocated_total,
        unallocated_amount=total - allocated_total,
        calculation_json=json.dumps({"allocations": allocations, "total_allocated": str(allocated_total)}),
    )
    db.session.add(alloc)
    return {"method": method.value, "allocated": str(allocated_total)}


def _apply_adjustment_to_item(item: ReceiptLineItem, adj_type: AdjustmentType, amount: Decimal):
    if adj_type == AdjustmentType.FEE:
        item.line_fee = (item.line_fee or Decimal("0")) + amount
    elif adj_type == AdjustmentType.DISCOUNT:
        item.line_discount = (item.line_discount or Decimal("0")) + amount
    elif adj_type == AdjustmentType.TIP:
        item.line_tip_allocation = (item.line_tip_allocation or Decimal("0")) + amount
    elif adj_type == AdjustmentType.DEPOSIT:
        item.line_deposit = (item.line_deposit or Decimal("0")) + amount


def set_line_allocation(
    line_item_id: int,
    allocation_type: str,
    amount: Decimal | None = None,
    percent: Decimal | None = None,
    market_id: int | None = None,
    custom_job_id: int | None = None,
    inventory_item_id: int | None = None,
    expense_category_id: int | None = None,
) -> ReceiptLineAllocation | None:
    item = db.session.get(ReceiptLineItem, line_item_id)
    if not item:
        return None

    alloc = ReceiptLineAllocation(
        receipt_line_item_id=line_item_id,
        allocation_type=allocation_type,
        amount=amount or item.line_total or Decimal("0"),
        percent=percent or Decimal("100"),
        market_id=market_id,
        custom_job_id=custom_job_id,
        inventory_item_id=inventory_item_id,
        expense_category_id=expense_category_id,
    )
    db.session.add(alloc)
    db.session.commit()
    return alloc


def bulk_assign_line_items(
    line_item_ids: list[int],
    allocation_type: str,
    market_id: int | None = None,
    custom_job_id: int | None = None,
    inventory_item_id: int | None = None,
) -> int:
    count = 0
    for item_id in line_item_ids:
        item = db.session.get(ReceiptLineItem, item_id)
        if not item:
            continue
        ReceiptLineAllocation.query.filter_by(receipt_line_item_id=item_id).delete()
        alloc = ReceiptLineAllocation(
            receipt_line_item_id=item_id,
            allocation_type=allocation_type,
            amount=item.line_total or Decimal("0"),
            percent=Decimal("100"),
            market_id=market_id,
            custom_job_id=custom_job_id,
            inventory_item_id=inventory_item_id,
        )
        db.session.add(alloc)
        count += 1
    db.session.commit()
    return count


def get_reconciliation_summary(receipt_id: int) -> dict[str, Any]:
    receipt = db.session.get(Receipt, receipt_id)
    if not receipt:
        return {}

    items = ReceiptLineItem.query.filter_by(receipt_id=receipt_id).all()
    adjustments = ReceiptAdjustmentAllocation.query.filter_by(receipt_id=receipt_id).all()

    line_subtotal = sum(i.line_subtotal or Decimal("0") for i in items)
    line_discount = sum(i.line_discount or Decimal("0") for i in items)
    line_tax = sum(i.line_tax or Decimal("0") for i in items)
    line_fees = sum(i.line_fee or Decimal("0") for i in items)
    adjustments_by_type = {a.adjustment_type: a for a in adjustments}

    calculated_total = line_subtotal + line_tax + line_fees - line_discount
    grand_total = receipt.grand_total or Decimal("0")
    difference = calculated_total - grand_total

    return {
        "parsed_line_subtotal": line_subtotal,
        "receipt_subtotal": receipt.subtotal,
        "allocated_tax": line_tax,
        "receipt_tax": receipt.tax_total,
        "allocated_fees": line_fees,
        "receipt_fees": receipt.fee_total,
        "allocated_discounts": line_discount,
        "receipt_discounts": receipt.discount_total,
        "calculated_total": calculated_total,
        "receipt_total": grand_total,
        "difference": difference,
        "adjustments": {
            str(k): {
                "method": v.allocation_method.value if v else None,
                "source": v.source_amount,
                "allocated": v.allocated_amount,
                "unallocated": v.unallocated_amount,
            }
            for k, v in adjustments_by_type.items()
        },
    }
