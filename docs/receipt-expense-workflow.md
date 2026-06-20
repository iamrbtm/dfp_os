# Receipt & Expense Workflow

This document describes the receipt management feature — from uploading a receipt image to approving expenses in the DFP OS ledger.

## Overview

Receipts flow through a pipeline:

```
Upload → Preprocess → OCR → AI Extraction → Review → Assign Allocations → Approve → Create Expenses
```

Each step is tracked. Duplicates are detected before approval.

## Status Lifecycle

| Status | Meaning |
|--------|---------|
| `UPLOADED` | File received, processing queued |
| `PROCESSING` | OCR/AI extraction in progress |
| `NEEDS_REVIEW` | Extraction complete, awaiting human review |
| `POSSIBLE_DUPLICATE` | Matched an existing receipt; user must resolve |
| `REJECTED` | Not a valid receipt or duplicate |
| `APPROVED` | Reviewed, allocated, expenses created |

## Routes

| URL | Purpose |
|-----|---------|
| `/expenses/receipts/` | Dashboard — summary counts and quick actions |
| `/expenses/receipts/upload` | Upload receipt image(s) |
| `/expenses/receipts/inbox` | List all non-approved/non-rejected receipts |
| `/expenses/receipts/review/<id>` | Review extracted data, approve/reject |
| `/expenses/receipts/assign/<id>` | Assign line items to allocation categories |
| `/expenses/receipts/duplicates/<id>` | Resolve a possible duplicate |
| `/expenses/receipts/<id>` | Receipt detail page |
| `/expenses/receipts/settings` | Receipt processing settings |
| `/expenses/receipts/help` | This workflow reference |

## Upload

1. Go to **Expenses → Receipts → Upload**.
2. Drag-and-drop one or more images, or click to select files.
3. Accepted formats: PNG, JPG, JPEG, PDF, HEIC, WEBP, BMP, TIFF.
4. Max file size: configured via `MAX_CONTENT_LENGTH_MB` (default 16 MB).
5. Files are stored under the configured `RECEIPT_STORAGE_PATH`.

After upload, each receipt is queued for background processing.

## Processing Pipeline

Processing runs automatically on upload:

1. **Preprocess** — OpenCV converts to grayscale and applies thresholding for better OCR accuracy.
2. **OCR** — Tesseract (primary), EasyOCR (fallback), or PaddleOCR extracts raw text.
3. **AI Extraction** — Ollama (local), OpenAI, or mock mode parses extracted text into structured fields (merchant, date, totals, line items).
4. **Duplicate Check** — Weighted comparison using file hash, merchant name, date, total, and receipt number.

Results are stored with confidence scores. Items below the configured threshold are flagged.

## Review

In the review screen you can:

- View the original receipt image
- Edit extracted fields (merchant, date, totals)
- Edit/add/remove line items
- Run tax/fee allocation
- Approve or reject

## Allocation Engine

Line items can be assigned to allocation categories:

| Allocation Type | Use |
|----------------|-----|
| `MARKET` | Vendor market booth fees, market-specific costs |
| `CUSTOM_ORDER` | Materials for a specific custom order |
| `INVENTORY` | Filament, supplies, general inventory |
| `GENERAL_EXPENSE` | Office, utilities, general business |
| `EQUIPMENT` | Tools, printer parts, equipment |
| `SHIPPING` | Postage, shipping supplies |
| `MARKETING` | Ads, signage, promotional materials |
| `OTHER` | Anything not fitting above |

### Tax/Fee Allocation

The engine distributes tax, fees, discounts, tip, and deposit amounts proportionally across taxable/non-taxable items using weighted distribution by subtotal. Penny rounding is handled by assigning remainder to the largest item.

### Split Allocations

A single line item can be split across multiple allocation types (e.g. 60% Market, 40% General Expense). Total allocations per line item must not exceed the line total.

### Adjustments

Use adjustments to modify allocations after approval:

| Adjustment Type | Use |
|----------------|-----|
| `ALLOCATION_CHANGE` | Move amount between allocation types |
| `REALLOCATION` | Full reallocation of line item |
| `LINE_ITEM_SPLIT` | Split an existing line item |
| `LINE_ITEM_MERGE` | Merge line items |
| `CORRECTION` | Fix data entry error |

## Duplicate Detection

Duplicates are detected on a weighted scale (0-1):

| Factor | Weight |
|--------|--------|
| File hash (exact) | 1.0 — automatic duplicate |
| Merchant name similarity | 0.30 |
| Receipt number match | 0.35 |
| Date match | 0.15 |
| Total match | 0.20 |

A score >= 0.70 triggers `POSSIBLE_DUPLICATE`. User can:
- **Keep** — clear flag, continue to review
- **Reject duplicate** — mark as duplicate, archive

Strictness is configurable via `RECEIPT_DUPLICATE_STRICTNESS` (loose/normal/strict).

## Approval

When a receipt is approved:

1. Status changes to `APPROVED`
2. Expenses are created for each allocated line item
3. Expense entries link back to the receipt via `receipt_id`
4. Expense amounts come from allocation amounts
5. The original receipt remains as a source record

## Audit Logging

All receipt actions are recorded via the audit-log microservice:

- Upload
- Processing start/complete
- Review/approve/reject
- Allocation changes
- Duplicate resolution

The audit microservice endpoint is configurable:
```
AUDIT_LOG_BASE_URL=http://audit-log-service:8090
AUDIT_LOG_TOKEN=change-me-audit-token
```

If the microservice is unreachable, receipt operations proceed with a warning.

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `RECEIPT_STORAGE_PATH` | `uploads/receipts` | Where uploaded files are stored |
| `RECEIPT_ALLOWED_EXTENSIONS` | `png,jpg,jpeg,pdf,heic,webp,bmp,tiff` | Accepted file types |
| `RECEIPT_MAX_FILES` | `10` | Max files per upload |
| `RECEIPT_OCR_ENGINE` | `tesseract` | OCR engine: tesseract, easyocr, paddleocr |
| `RECEIPT_AI_PROVIDER` | `ollama` | AI provider: ollama, openai, mock |
| `RECEIPT_AI_MODEL` | `llama3.2` | AI model name |
| `RECEIPT_AI_API_URL` | `http://localhost:11434/api/generate` | AI API endpoint |
| `RECEIPT_AI_API_KEY` | — | API key for OpenAI |
| `RECEIPT_DUPLICATE_STRICTNESS` | `normal` | loose/normal/strict |
| `RECEIPT_LOW_CONFIDENCE_THRESHOLD` | `0.80` | Items below this are flagged |
| `AUDIT_LOG_BASE_URL` | `http://audit-log-service:8090` | Audit microservice URL |
| `AUDIT_LOG_TOKEN` | — | Audit microservice auth token |
| `AUDIT_LOG_ENABLED` | `false` | Enable/disable audit logging |
