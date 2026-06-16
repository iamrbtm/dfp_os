Copilot Prompt: Expand DFP OS Expenses into Receipt-Centered Expense Management

You are working inside the main DFP OS application, not the audit-log microservice. Treat the existing DFP OS app as the source of truth for architecture, UI conventions, naming, database patterns, auth, routing, analytics, inventory, markets, jobs, and app-wide styling. Before coding, inspect the current repository and align with the existing stack, patterns, linting, tests, and database migration workflow.

Goal

Replace the current manual-first Expenses experience with a receipt-centered expense workflow. The new feature should live under the Expenses area as a Receipts submenu/page, but it should become the primary intake path for expenses. Keep the underlying expense ledger/reporting concepts intact. Do not simply delete the existing expense model unless the repo clearly shows it is safe to do so. Instead, evolve expenses so receipts, receipt line items, allocations, taxes, fees, and audit history flow into expense reporting, market profitability, custom job profitability, inventory, and analytics.

This is an all-at-once implementation. You may internally organize the work into phases, but do not build a tiny V1 that leaves the hard pieces for later. Implement the full architecture now in a maintainable way.

Current DFP OS Context

Use the main DFP OS context from the repo and prior project direction:

* Business app for Dudefish Printing / DFP OS.
* Existing modules include Markets, Expenses, Analytics, Inventory, POS / business operations, and custom jobs.
* Main app direction has favored Python with uv, Python 3.14 compatibility where possible, database-backed features, and clean integration across the whole program.
* Do not use the audit-log microservice stack as the base for this feature.
* If the repo uses a different frontend/backend/database than expected, follow the actual repo.

Feature Summary

Create a receipt management system where users can:

1. Upload receipt images or PDFs.
2. Capture receipts using the browser/device camera where supported.
3. Import common receipt formats: JPG, JPEG, PNG, HEIC/HEIF, PDF, and multi-page PDF/image receipts.
4. Store the original receipt file for audit/tax proof.
5. OCR and parse the receipt locally by default.
6. Use a local AI cleanup/extraction step through Ollama.
7. Review and edit all parsed metadata and line items before approval.
8. Assign every receipt line item to a Market, Custom Job, Inventory, General Business Expense, Personal/Excluded, or split allocation.
9. Bulk assign all line items to a single Market, Custom Job, category, or inventory workflow.
10. Reverse-allocate taxes, fees, discounts, deposits, tips, coupons, and rounding adjustments back to individual line items when possible.
11. Create accounting-ready expense records from the approved receipt.
12. Feed Markets, Custom Jobs, Inventory, Expenses, Analytics, and reporting.
13. Detect duplicates before approval.
14. Track confidence scores and highlight low-confidence fields.
15. Include an in-app downloadable Markdown help/spec document linked from the receipt page.

Architecture Decision

Use a provider-based receipt parsing architecture.

Local-first default

Implement these local providers first:

1. Image preprocessing provider
    * Normalize orientation using EXIF data.
    * Deskew where possible.
    * Crop/clean borders when safe.
    * Convert HEIC/HEIF to a supported image format.
    * Convert PDFs to page images.
    * Generate thumbnails/previews.
    * Preserve the original file unchanged.
2. OCR/document parsing provider
    * Preferred: PaddleOCR / PaddleOCR-VL where compatible with the repo environment.
    * Fallback: Tesseract/EasyOCR only if PaddleOCR is not practical in the local environment.
    * Save raw OCR text, token/page geometry if available, structured output if available, and parser diagnostics.
3. Local AI structured extraction provider
    * Use Ollama as the local LLM/VLM runtime.
    * Recommended model: qwen2.5vl for receipt image/document understanding and structured output.
    * Preferred model size should be configurable:
        * qwen2.5vl:7b or the closest available 7B-ish model for normal local hardware.
        * Larger Qwen2.5-VL variants if the host has enough VRAM/RAM.
        * Smaller/quantized model only if needed for low-resource systems.
    * The app must not hard-code the model. Use settings/env configuration.

Optional API fallback

Design the parser interface so third-party providers can be added later without rewriting the receipt module. Add configuration placeholders for:

* Taggun
* Mindee
* Veryfi
* Generic webhook/API provider

Do not make a paid API required for the feature to work.

Environment / Configuration

Add documented environment variables or settings consistent with the repo style:

* RECEIPT_STORAGE_DRIVER=local
* RECEIPT_STORAGE_PATH=...
* RECEIPT_MAX_UPLOAD_MB=25
* RECEIPT_ALLOWED_TYPES=image/jpeg,image/png,image/heic,image/heif,application/pdf
* RECEIPT_OCR_PROVIDER=paddleocr
* RECEIPT_AI_PROVIDER=ollama
* OLLAMA_BASE_URL=http://localhost:11434
* OLLAMA_RECEIPT_MODEL=qwen2.5vl:7b
* RECEIPT_ENABLE_API_FALLBACK=false
* RECEIPT_API_PROVIDER=
* TAGGUN_API_KEY=
* MINDEE_API_KEY=
* VERYFI_CLIENT_ID=
* VERYFI_CLIENT_SECRET=
* RECEIPT_DUPLICATE_STRICTNESS=normal
* RECEIPT_LOW_CONFIDENCE_THRESHOLD=0.80

Use whatever config mechanism the repo already uses. Do not expose secrets in the frontend.

UX / Navigation

Add a Receipts submenu under Expenses.

Suggested pages/routes:

* Expenses > Receipts Dashboard
* Expenses > Receipts Inbox
* Expenses > Upload / Capture Receipt
* Expenses > Needs Review
* Expenses > Approved Receipts
* Expenses > Duplicate Warnings
* Expenses > Receipt Settings
* Expenses > Receipt Help / Markdown Spec

The dashboard should show:

* Total receipts this month.
* Receipts needing review.
* Possible duplicates.
* Total approved expense amount.
* Unallocated amount.
* Recently uploaded receipts.
* Top stores/vendors.
* Spending by Market.
* Spending by Custom Job.
* Spending by expense category.
* Inventory-prompted items waiting to become inventory.

Upload / Capture Requirements

Build a clean upload flow that supports:

* Drag-and-drop upload.
* File picker upload.
* Camera capture using browser/device APIs where available.
* Mobile-friendly capture page.
* Multiple file upload.
* Multi-page PDF handling.
* Preview before upload.
* Upload progress.
* Validation of file type and size.
* Friendly errors.
* Retry failed parsing.

Each uploaded receipt should enter an Inbox / Processing state before becoming editable.

Receipt Processing Workflow

Use this state machine or adapt to existing repo conventions:

* uploaded
* preprocessing
* ocr_processing
* ai_extracting
* needs_review
* possible_duplicate
* approved
* rejected
* archived
* processing_failed

Users should be able to manually re-run parsing, switch provider, or mark a receipt as unreadable.

Data Model

Inspect existing models first. Extend existing Expense, Market, Custom Job, Inventory, User, Attachment/File, Category, and Audit models where appropriate. Avoid duplicate concepts.

Add or adapt models equivalent to the following.

Receipt

Fields:

* id
* user_id / created_by_id
* status
* original_file_id
* preview_file_id / thumbnail_file_id
* source_type: upload, camera, email_import_future, manual
* file_hash
* perceptual_image_hash if practical
* raw_ocr_text
* raw_ocr_json
* ai_extracted_json
* final_reviewed_json
* parser_provider
* parser_model
* parser_version
* confidence_overall
* low_confidence_flags
* merchant_name
* merchant_normalized_id / vendor_id if available
* store_name
* store_number
* address_line_1
* address_line_2
* city
* state
* postal_code
* country
* phone
* website
* receipt_number
* transaction_number
* register_number
* cashier_name_or_id
* date_time
* timezone
* subtotal
* tax_total
* fee_total
* discount_total
* tip_total
* deposit_total
* rounding_adjustment
* grand_total
* payment_method
* payment_card_brand
* payment_card_last4
* currency
* duplicate_group_id / duplicate_score
* approved_at
* approved_by_id
* rejected_at
* rejected_by_id
* notes
* created_at
* updated_at
* deleted_at if soft deletes exist

ReceiptLineItem

Fields:

* id
* receipt_id
* row_order
* raw_text
* description
* normalized_description
* sku
* upc
* quantity
* unit_of_measure
* unit_price
* line_subtotal
* line_discount
* line_tax
* line_fee
* line_deposit
* line_tip_allocation
* line_total
* taxable_status: taxable, non_taxable, unknown
* category_id
* confidence_description
* confidence_price
* confidence_quantity
* confidence_tax
* needs_review
* is_inventory_candidate
* is_personal_or_excluded
* notes
* created_at
* updated_at

ReceiptLineAllocation

Each line item can have one or many allocations. Full split support is required now.

Fields:

* id
* receipt_line_item_id
* allocation_type: market, custom_job, inventory, general_expense, personal_excluded
* market_id nullable
* custom_job_id nullable
* inventory_item_id nullable
* expense_category_id nullable
* amount
* percent
* quantity_allocated nullable
* notes
* created_at
* updated_at

Rules:

* Allocations for a line item must total either 100% or the full line total unless explicitly marked unresolved.
* Support amount-based split and percentage-based split.
* UI must show clear validation errors if split totals are off.

ReceiptAdjustmentAllocation

Track tax, fee, discount, deposit, tip, and rounding allocation math.

Fields:

* id
* receipt_id
* adjustment_type: tax, fee, discount, deposit, tip, rounding
* allocation_method: exact, taxable_proportional, subtotal_proportional, category_rule, manual, unallocated
* source_amount
* allocated_amount
* unallocated_amount
* calculation_json
* created_at
* updated_at

Expense Records

When a receipt is approved, create or update official expense ledger entries. Prefer one of these patterns depending on the existing codebase:

* One expense header per receipt with child expense lines, or
* One expense per allocation with a shared receipt_id, or
* Existing expense model extended to support receipt_id and line allocation detail.

Do not double-count receipt expenses in reporting.

Metadata Extraction

The parser must attempt to extract:

* Merchant/store name
* Normalized vendor/store identity
* Address
* Phone
* Website if present
* Store number
* Register number
* Cashier name/id
* Receipt number
* Transaction number
* Date/time
* Timezone if inferable
* Payment method
* Card brand and last 4 if present
* Subtotal
* Tax total
* Fees
* Deposits
* Discounts/coupons
* Tips
* Total
* Currency
* Line items with quantity, unit price, total price, discounts, SKU/UPC if present

Show extracted values beside confidence indicators.

AI Extraction Contract

Create a strict JSON schema for the AI extraction result. The local AI provider must validate the JSON response before storing it.

The model prompt should tell the model:

* Return JSON only.
* Do not invent missing fields.
* Use null for unknown fields.
* Preserve raw text where uncertain.
* Include confidence scores from 0 to 1.
* Flag fields needing human review.
* Extract line items only from actual purchased items, not summary totals, payment lines, tax summary lines, or coupons unless coupons affect a line item.

If the model returns invalid JSON, retry with a repair prompt once, then fail gracefully and leave receipt in needs_review or processing_failed with the raw OCR text available.

Review / Edit Screen

Build a strong review UI. This is not optional.

The review screen should include:

* Receipt image/PDF preview on one side.
* Parsed metadata form on the other side.
* Line item table below or beside it.
* Clickable source highlighting if OCR geometry is available.
* Low-confidence fields visually marked.
* Editable fields.
* Add/remove line items.
* Merge/split line items.
* Recalculate totals.
* Manual override for taxes, fees, discounts, tips, deposits, and rounding.
* Notes field.
* Save draft.
* Approve receipt.
* Reject receipt.
* Re-run OCR/extraction.

Assignment UX

Each line item must be assignable to:

* Market
* Custom Job
* Inventory
* General Business Expense
* Personal/Excluded

Add controls for:

* Assign selected line items.
* Assign all line items to one Market.
* Assign all line items to one Custom Job.
* Assign all line items to one category.
* Assign all unassigned items.
* Split one line across multiple destinations by percent or amount.
* Save assignment templates/rules by vendor/store.

Examples:

* Costco receipt can split between a Market, a Custom Job, Inventory, and excluded personal items.
* A filament purchase can prompt an Inventory creation/update window.
* A booth fee can be assigned directly to a Market.
* Materials for one custom order can be assigned to that Custom Job.

Inventory Prompt Behavior

When a line item is categorized as inventory or likely inventory:

1. Prompt the user with a modal or side panel.
2. Let the user choose:
    * Add to existing inventory item.
    * Create new inventory item.
    * Mark as consumable supply.
    * Ignore inventory for this line.
3. Prefill likely fields:
    * Name
    * SKU/UPC
    * Quantity
    * Unit cost
    * Vendor/store
    * Purchase date
    * Receipt reference
4. After confirmation, link the receipt line allocation to the inventory record.

Do not automatically create inventory without user confirmation.

Tax / Fee / Discount Reverse Allocation

Implement an allocation engine that can reverse-calculate receipt-level adjustments back to line items.

Supported adjustments:

* Sales tax
* Environmental fees
* Service fees
* Bottle/can deposits
* Tips
* Discounts
* Coupons
* Rewards/store credits
* Rounding adjustments

Required allocation methods:

1. Exact line-level extraction
    * If tax/fee/discount is shown per line, use that exact amount.
2. Taxable proportional allocation
    * If tax total exists but line tax does not, allocate tax across taxable line items by taxable subtotal.
    * If taxable status is unknown, infer from categories but mark as review needed.
3. Subtotal proportional allocation
    * For fees/tips when no better source exists, allocate by line subtotal.
4. Discount allocation
    * If discount is tied to a line, apply to that line.
    * If receipt-level discount is not tied to a line, allocate proportionally across eligible items.
5. Manual override
    * User can override any calculated allocation.
6. Unallocated bucket
    * If the math cannot be reconciled safely, store the difference as unallocated and require review before approval unless the difference is within a small configured tolerance.

Rounding:

* Use decimal/currency-safe math. Do not use floating point for money.
* Allocate pennies deterministically using largest-remainder method or another stable method.
* Preserve calculation details in ReceiptAdjustmentAllocation.calculation_json.
* Show the user a reconciliation summary:
    * Parsed line subtotal
    * Receipt subtotal
    * Allocated tax
    * Allocated fees
    * Allocated discounts
    * Calculated grand total
    * Receipt grand total
    * Difference

Duplicate Detection

Implement duplicate detection before approval.

Use a weighted score from:

* File hash exact match
* Image perceptual hash similarity if available
* Merchant/store match
* Date/time closeness
* Grand total match
* Receipt number / transaction number match
* Payment card last 4 match
* Line item similarity

If duplicate risk is high:

* Move or flag receipt as possible_duplicate.
* Show likely duplicate receipts.
* Let the user choose:
    * Merge/keep existing
    * Save as separate receipt
    * Reject duplicate

Reporting / Analytics Integration

The receipt system must feed these areas:

* Expense dashboard
* Market profitability
* Custom job profitability
* Inventory purchase history
* Vendor/store spending
* Monthly expense reports
* Category spending
* Tax summaries
* Unallocated receipt report
* Duplicate receipt report
* Receipt audit log

Reports must avoid double-counting. Approved receipt allocations should be the source of truth for receipt-driven expenses.

Permissions / Roles

Follow existing auth/role patterns. If roles exist, implement recommended permissions:

* Owner/Admin: full access, settings, delete/archive, approve, override duplicates.
* Manager: upload, edit, approve, assign, create inventory prompts.
* Employee/Staff: upload/capture receipts, view own uploads, edit drafts if allowed.
* Read-only: view only.

If no role system exists, implement safe hooks/checks that can be wired into the existing system without blocking development.

Audit Trail

Record audit events for:

* Receipt uploaded
* OCR started/completed/failed
* AI extraction started/completed/failed
* Metadata edited
* Line item edited
* Allocation changed
* Tax/fee allocation recalculated
* Inventory prompt accepted/ignored
* Duplicate warning created/resolved
* Receipt approved/rejected/archived
* Expense ledger record created/updated

Use the main DFP OS audit/event pattern if one exists. Do not integrate with the separate audit-log microservice unless the main app already does.

In-App Markdown Help / Downloadable Spec

Create a Markdown document in the app content/docs area named something like:

* receipt-expense-workflow.md

Link it from the Receipts page as “Receipt Workflow Help” or similar. Let the user view and download it if the app supports downloads.

The Markdown should explain:

* How receipt upload/capture works.
* What OCR and AI extraction do.
* What confidence scores mean.
* How to review/edit parsed fields.
* How to assign line items.
* How split allocations work.
* How taxes/fees/discounts are allocated.
* How inventory prompts work.
* How duplicate detection works.
* How approved receipts flow into expenses, markets, jobs, inventory, and analytics.
* Known limitations and best practices for taking receipt photos.

Error Handling

Handle:

* Unsupported file type
* File too large
* Corrupt image/PDF
* HEIC conversion failure
* OCR failure
* Ollama unavailable
* Model unavailable
* Invalid AI JSON
* Provider timeout
* Duplicate found
* Totals do not reconcile
* Split allocations do not total correctly
* Inventory creation failure
* Permission denied

All errors should be understandable to a normal user and useful to a developer.

Testing Requirements

Add or update tests for:

* File upload validation
* Receipt model/database migrations
* OCR provider interface with mocked provider
* Ollama provider with mocked response
* AI JSON schema validation
* Invalid JSON repair/failure path
* Metadata parsing
* Line item parsing
* Tax/fee/discount allocation math
* Penny rounding behavior
* Split allocation validation
* Bulk assignment behavior
* Inventory prompt workflow
* Duplicate detection scoring
* Expense ledger creation from approved receipt
* Reporting integration without double-counting
* Permissions
* UI review flow where test framework supports it

Use fixtures for receipts. Do not commit real sensitive receipts.

Acceptance Criteria

The work is complete when:

1. Expenses has a Receipts submenu/page.
2. User can upload or camera-capture a receipt where supported.
3. JPG, PNG, HEIC/HEIF, PDF, and multi-page receipts are handled or gracefully rejected with clear explanation.
4. Original receipt files are stored unchanged.
5. Local OCR runs by default.
6. Local Ollama/Qwen extraction is supported and configurable.
7. Parsed metadata and line items are saved.
8. User can review and edit everything before approval.
9. Every line item can be assigned to Market, Custom Job, Inventory, General Expense, Personal/Excluded, or split across multiple destinations.
10. Bulk assignment works.
11. Inventory line items can open a create/update inventory prompt.
12. Taxes, fees, discounts, tips, deposits, and rounding can be allocated back to line items with transparent math.
13. Duplicate detection warns before approval.
14. Approved receipts create/update official expense records.
15. Receipt data feeds Markets, Custom Jobs, Inventory, Expenses, Analytics, and reports.
16. Confidence scores and low-confidence review flags are visible.
17. Receipt workflow Markdown help is linked from the page and downloadable where supported.
18. Permission checks follow the existing app pattern.
19. Audit/history events are recorded using the main DFP OS pattern.
20. Tests cover the important parsing, allocation, duplicate, approval, and reporting logic.

Implementation Notes

* Use decimal-safe money math everywhere.
* Keep parser providers replaceable.
* Keep AI optional but supported.
* Do not trust OCR/AI output without validation.
* Never auto-approve a receipt.
* Never create inventory records without user confirmation.
* Avoid double-counting expenses.
* Keep the UI friendly. Receipt parsing is messy. The user needs confidence, not magic tricks.
* Follow existing code style exactly.
* Add migrations, tests, and documentation.
* Update navigation and analytics wiring.
* Make this feel native to DFP OS, not bolted on.