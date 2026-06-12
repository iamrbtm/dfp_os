# DESIGN.md

# Dude Fish OS Design Specification

## 1. Vision

Dude Fish OS is a complete Flask-based business platform for Dude Fish Printing.

It combines:

1. Public website
2. Admin dashboard
3. Mobile-friendly POS
4. Operations system
5. Analytics system
6. REST API

The owner should be able to prepare products before moving to Tennessee, then start selling, tracking, printing, and analyzing from day one.

Core question:

> What should Dude Fish Printing make, sell, restock, stop selling, or improve next?

## 2. Main Business Goals

- Relaunch Dude Fish Printing cleanly in Clarksville, Tennessee.
- Grow toward $4,000-$5,000/month profit.
- Support online sales, Facebook sales, vendor markets, word of mouth, and local business outreach.
- Keep the fun family-friendly side of the brand.
- Add professional manufacturing and small business services.
- Track enough data to make real decisions.
- Avoid relying on memory, notes, and random spreadsheets.

## 3. Target Users

### Owner/Admin

Needs full access to products, POS, orders, inventory, markets, expenses, analytics, API tokens, settings, and user management.

### Staff/Helper

Needs POS, inventory updates, print job updates, order fulfillment, and market packing views.

### Public Customer

Needs product examples, custom order form, contact form, market schedule, and basic information.

### Business Customer

Needs small business product examples, quote request form, upload field, deadline field, and budget/notes fields.

## 4. Brand and UI Direction

Public site:

- Warm
- Colorful
- Family-run
- Friendly
- Creative
- Trustworthy

Admin/POS:

- Fast
- Clean
- Practical
- Mobile-friendly
- Not cluttered

Design style:

- Tailwind CSS
- Cards
- Rounded corners
- Clear buttons
- Good spacing
- Responsive layouts
- Large POS buttons
- Clear table actions
- Useful empty states

## 5. Technical Architecture

Backend:

- Flask app factory
- SQLAlchemy models
- MariaDB
- Flask-Migrate
- Flask-Login
- Flask-WTF
- Service layer
- API schemas
- Token auth

Frontend:

- Jinja2 templates
- Tailwind CSS
- Vanilla JS
- HTMX
- Alpine.js sparingly
- Chart.js

Deployment:

- Dockerfile
- docker-compose.yml
- Gunicorn
- `.env.example`
- MariaDB container for local dev

## 6. Blueprints

Use these blueprints:

- `public`
- `auth`
- `dashboard`
- `products`
- `inventory`
- `printers`
- `print_jobs`
- `customers`
- `orders`
- `custom_orders`
- `markets`
- `expenses`
- `analytics`
- `pos`
- `api`
- `settings`

## 7. Core Data Models

### Users

Fields:

- id
- email
- password_hash
- first_name
- last_name
- role
- is_active
- last_login_at
- created_at
- updated_at

Roles:

- Admin
- Staff
- Viewer
- API-only

### API Tokens

Fields:

- id
- user_id
- name
- token_hash
- prefix
- scopes
- last_used_at
- expires_at
- revoked_at
- created_at
- updated_at

Show raw token only once. Store only hash.

### Categories

Fields:

- id
- name
- slug
- description
- sort_order
- is_public
- is_pos_visible
- created_at
- updated_at

Examples:

- Dragons
- Fidgets
- Flexi Animals
- Personalized Gifts
- Clarksville Collection
- Military-Family-Safe Gifts
- Small Business Products
- Custom Orders
- Clearance

### Collections

Fields:

- id
- name
- slug
- description
- is_public
- sort_order
- created_at
- updated_at

Examples:

- The Dragon Den
- Fidget Fish & Friends
- Clarksville Collection
- Homecoming & Moving Collection
- Small Biz Boosters
- Market Best Sellers

### Products

Fields:

- id
- name
- slug
- sku_base
- short_description
- description
- category_id
- collection_id
- product_type
- status
- is_public
- is_pos_visible
- is_featured
- base_price
- estimated_material_cost
- estimated_labor_minutes
- estimated_print_minutes
- estimated_profit
- default_image_path
- tags
- care_instructions
- safety_notes
- license_status
- design_source
- commercial_license_notes
- created_at
- updated_at
- deleted_at

Statuses:

- Draft
- Active
- Hidden
- Retired
- Needs Review

Types:

- Finished Good
- Customizable Product
- Made-to-Order Product
- POS Quick Item
- B2B Product
- Internal Only

### Product Variants

Fields:

- id
- product_id
- sku
- name
- colorway
- size
- material_type
- price
- material_cost
- estimated_print_minutes
- estimated_filament_grams
- active
- pos_button_label
- pos_sort_order
- barcode_or_qr_code
- created_at
- updated_at

### Model Assets / License Tracking

Fields:

- id
- title
- source_type
- source_url
- designer_name
- license_type
- commercial_use_allowed
- license_expiration
- proof_of_license_path
- file_location
- related_product_id
- notes
- status
- created_at
- updated_at

Source types:

- Self-designed
- Purchased STL
- Subscription Library
- Free Model
- Customer-Provided
- Commissioned Design
- Unknown

License statuses:

- Unknown
- Personal Only
- Commercial Allowed
- Commercial Subscription
- Customer-Owned
- Needs Review
- Restricted
- Retired

### Printers

Fields:

- id
- name
- model
- serial_number
- status
- location
- has_ams
- default_nozzle_size
- notes
- purchase_date
- maintenance_notes
- total_print_hours
- created_at
- updated_at

Statuses:

- Active
- Idle
- Printing
- Maintenance
- Broken
- Retired

Seed:

- Bambu A1 #1
- Bambu A1 #2
- Bambu A1 #3
- Bambu A1 #4
- Bambu X1 Carbon #1
- Bambu X1 Carbon #2 - Broken
- Bambu P1P #1
- Bambu P1P #2

### AMS Units

Fields:

- id
- name
- type
- status
- assigned_printer_id
- slot_count
- notes
- created_at
- updated_at

Seed:

- AMS Lite #1
- AMS Lite #2
- AMS Lite #3
- AMS Lite #4
- Standard AMS #1

### Filament Spools

Fields:

- id
- brand
- material_type
- color_name
- color_hex
- spool_weight_grams
- remaining_weight_grams
- cost_per_spool
- cost_per_gram
- supplier
- purchase_date
- storage_location
- status
- reorder_threshold_grams
- notes
- created_at
- updated_at

Statuses:

- New
- Active
- Low
- Empty
- Archived

### Inventory Locations

Fields:

- id
- name
- type
- description
- active
- created_at
- updated_at

Examples:

- Home Inventory
- Market Bin
- Website Stock
- Finished Goods Shelf
- Custom Order Hold
- Damaged/Seconds

### Finished Goods Inventory

Fields:

- id
- product_id
- variant_id
- location_id
- quantity_on_hand
- quantity_reserved
- reorder_threshold
- reorder_target
- last_counted_at
- created_at
- updated_at

Calculated:

- quantity_available = quantity_on_hand - quantity_reserved

Features:

- Adjust stock
- Transfer stock
- Deduct POS sales
- Reserve for orders
- Low stock alerts
- Reprint suggestions

### Customers

Fields:

- id
- first_name
- last_name
- display_name
- email
- phone
- customer_type
- business_name
- address_line1
- address_line2
- city
- state
- postal_code
- notes
- marketing_opt_in
- created_at
- updated_at

Types:

- Retail
- Custom Order
- Business
- Vendor
- Event
- Wholesale
- Internal

### Orders

Fields:

- id
- order_number
- customer_id
- channel
- status
- subtotal
- discount_total
- tax_total
- shipping_total
- total
- amount_paid
- payment_status
- fulfillment_status
- due_date
- pickup_or_shipping
- related_market_id
- related_pos_session_id
- notes
- created_at
- updated_at

Channels:

- Website
- POS
- Facebook
- Vendor Market
- Word of Mouth
- Etsy
- Custom Order
- B2B
- Other

Statuses:

- Draft
- Quote Requested
- Quote Sent
- Approved
- In Production
- Ready for Pickup
- Shipped
- Completed
- Canceled
- Refunded

Payment statuses:

- Unpaid
- Partial
- Paid
- Refunded

### Order Items

Fields:

- id
- order_id
- product_id
- variant_id
- description
- quantity
- unit_price
- discount_amount
- line_total
- material_cost_estimate
- labor_minutes_estimate
- customization_text
- notes
- created_at
- updated_at

### Payments

Fields:

- id
- order_id
- pos_sale_id
- payment_method
- amount
- status
- external_reference
- received_at
- notes
- created_at
- updated_at

Methods:

- Cash
- External Card Placeholder
- Venmo
- Cash App
- Apple Pay
- Other

No card data.

### Custom Order Requests

Fields:

- id
- request_number
- customer_id
- request_type
- title
- description
- uploaded_file_path
- budget_range
- desired_due_date
- status
- quoted_price
- deposit_required
- deposit_paid
- quote_notes
- internal_notes
- converted_order_id
- source
- created_at
- updated_at

Types:

- Personalized Gift
- Military-Family-Safe Gift
- Small Business Display
- Event Favor
- Replacement Part
- General Custom Print
- POS Custom Request
- Other

Statuses:

- New
- Reviewing
- Need More Info
- Quote Sent
- Approved
- Rejected
- Converted to Order
- In Production
- Completed
- Archived

### Print Jobs

Fields:

- id
- job_number
- product_id
- variant_id
- order_id
- order_item_id
- printer_id
- status
- priority
- quantity
- estimated_print_minutes
- actual_print_minutes
- estimated_filament_grams
- actual_filament_grams
- estimated_material_cost
- actual_material_cost
- started_at
- completed_at
- due_date
- failure_reason
- notes
- created_at
- updated_at

Statuses:

- Queued
- Sliced
- Printing
- Paused
- Completed
- Failed
- Canceled
- Needs Reprint

### Vendor Markets

Fields:

- id
- name
- location_name
- address
- city
- state
- event_date
- start_time
- end_time
- booth_fee
- application_fee
- status
- expected_traffic
- actual_revenue
- actual_profit
- notes
- created_at
- updated_at

Statuses:

- Interested
- Applied
- Accepted
- Waitlisted
- Rejected
- Scheduled
- Completed
- Canceled
- Not Worth Repeating
- Repeat

### Market Packing List

Fields:

- id
- market_event_id
- product_id
- variant_id
- planned_quantity
- packed_quantity
- sold_quantity
- returned_quantity
- notes
- created_at
- updated_at

### POS Sessions

Fields:

- id
- session_number
- opened_by_user_id
- closed_by_user_id
- market_event_id
- inventory_location_id
- status
- opening_cash
- closing_cash
- expected_cash
- cash_difference
- opened_at
- closed_at
- notes
- created_at
- updated_at

Statuses:

- Open
- Closed
- Voided

### POS Sales

Fields:

- id
- pos_session_id
- order_id
- sale_number
- customer_id
- subtotal
- discount_total
- tax_total
- total
- payment_method
- amount_received
- change_due
- status
- notes
- created_at
- updated_at

Statuses:

- Draft
- Completed
- Voided
- Refunded

### POS Sale Items

Fields:

- id
- pos_sale_id
- product_id
- variant_id
- description
- quantity
- unit_price
- discount_amount
- line_total
- item_type
- custom_notes
- created_at
- updated_at

Item types:

- Product
- Custom Item
- Custom Order Deposit
- Discount
- Fee

### Expenses

Fields:

- id
- date
- vendor
- category
- description
- amount
- payment_method
- related_market_id
- related_order_id
- receipt_file_path
- tax_deductible
- notes
- created_at
- updated_at

Categories:

- Filament
- Printer Parts
- Tools
- Booth Fees
- Packaging
- Shipping
- Software
- Advertising
- Vehicle/Travel
- Office Supplies
- Licenses/Fees
- Other

### Settings

Fields:

- id
- key
- value
- value_type
- group
- description
- updated_at

Examples:

- business_name
- business_email
- business_phone
- default_tax_rate
- tax_enabled
- pos_card_processing_enabled
- pos_card_processor
- receipt_footer
- default_inventory_location
- upload_limit_mb

## 8. Public Website Pages

### Home

Sections:

- Hero
- Featured products
- Custom order CTA
- Small business CTA
- Market schedule preview
- Why choose Dude Fish Printing
- Gallery preview
- Contact CTA

### Shop / Gallery

Features:

- Product cards
- Category filters
- Collection filters
- Search
- Featured products
- Custom order CTA

Online checkout is not required in version 1. The page can drive requests/contact.

### Product Detail

Show:

- Name
- Image
- Description
- Starting price
- Category
- Customization availability
- Care notes
- Request/contact CTA

### Custom Orders

Include:

- Explanation of process
- Request form
- Upload field
- Budget range
- Desired due date
- Contact fields
- Confirmation message

### Small Business Products

Show:

- QR code signs
- Business card holders
- Product displays
- Price tag stands
- Vendor booth signs
- Event/table signs
- Bulk keychains/favors

### Military-Family-Safe Gifts

Show safe products:

- Welcome home signs
- PCS/moving keepsakes
- Family ornaments
- Luggage tags
- Generic dog-tag-style keychains
- Deployment countdown items
- Retirement/promotion party items without protected insignia

Include a note that official logos, marks, unit insignia, rank insignia, and trademarked designs require proper rights/permission.

### Market Schedule

Show upcoming markets:

- Name
- Date/time
- Location
- Notes
- Map link placeholder

### FAQ

Topics:

- Custom orders
- Turnaround time
- Materials
- Shipping/pickup
- Safety
- Color availability
- Market pickup
- Payment methods

## 9. Admin Dashboard

Cards:

- Today's POS revenue
- Month revenue
- Estimated month profit
- Open custom requests
- Orders in production
- Print jobs queued
- Active printers
- Low filament
- Low inventory
- Upcoming markets
- Expenses this month

Charts:

- Sales by channel
- Sales by category
- Revenue by week
- Top products
- POS payment methods
- Printer failure rate

Lists:

- Custom orders due soon
- Print jobs needing attention
- Products below reorder target
- Upcoming markets

## 10. POS Design

POS frontend implementation should be chosen for speed and maintainability. Jinja/HTMX/Alpine is acceptable if it stays responsive. A small Preact + TypeScript + Vite island is preferred if it makes the checkout flow cleaner under high-volume market conditions.

Main route:

```text
/pos
```

Supporting routes:

```text
/pos/sessions
/pos/sessions/new
/pos/sessions/<id>
/pos/sessions/<id>/close
/pos/sale/<id>/receipt
```

Mobile layout:

- Top bar with session, market, cart total
- Category tabs
- Search box
- Product grid
- Floating cart button
- Cart drawer
- Checkout button

Desktop layout:

- Left product grid
- Right cart

Product tiles:

- Name
- Price
- Image/color placeholder
- Stock indicator
- Tap/click adds item

Cart:

- Line items
- Quantity plus/minus
- Remove item
- Notes
- Discount
- Subtotal
- Tax
- Total
- Payment method
- Complete sale

Cash drawer / cash box behavior:

- Opening cash amount.
- Expected cash at close.
- Actual cash counted.
- Difference/over-short amount.
- Notes for discrepancies.
- Payment totals by method.

POS actions:

- Open session
- Select market
- Select inventory location
- Add product
- Add custom item
- Add custom order deposit
- Add customer
- Accept cash
- Record external payment
- Calculate change
- Complete sale
- Deduct inventory
- Create order/payment
- Show receipt
- Close session
- Show cash/payment summary

## 11. REST API

Base path:

```text
/api/v1/
```

Auth:

```http
Authorization: Bearer <token>
```

List response:

```json
{
  "data": [],
  "pagination": {
    "page": 1,
    "per_page": 25,
    "total": 0,
    "pages": 0
  }
}
```

Error response:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Validation failed.",
    "details": {}
  }
}
```

Required endpoints include CRUD for products, categories, collections, variants, model assets, printers, AMS units, filament spools, customers, orders, payments, custom requests, markets, market sales, POS sessions, POS sales, expenses, and settings.

Analytics endpoints:

```text
GET /api/v1/analytics/summary
GET /api/v1/analytics/products
GET /api/v1/analytics/markets
GET /api/v1/analytics/printing
GET /api/v1/analytics/inventory
GET /api/v1/analytics/pos
GET /api/v1/analytics/expenses
```

Export endpoints:

```text
GET /api/v1/exports/products.csv
GET /api/v1/exports/inventory.csv
GET /api/v1/exports/orders.csv
GET /api/v1/exports/custom-requests.csv
GET /api/v1/exports/markets.csv
GET /api/v1/exports/pos-sales.csv
GET /api/v1/exports/expenses.csv
```

## 12. Analytics

### Executive

- Revenue today
- Revenue this month
- Estimated profit
- POS revenue
- Open orders
- Open custom requests
- Print jobs queued
- Low inventory
- Low filament
- Upcoming markets

### Product

- Units sold
- Revenue
- Estimated profit
- Average sale price
- Inventory on hand
- Reorder suggestion
- Failure rate

### Market

- Revenue per market
- Profit per market
- Booth fee percentage
- Units sold
- Top products
- Payment method totals
- Repeat recommendation

### POS

- Sales by day/session
- Payment method totals
- Expected cash
- Actual cash
- Over/short
- Average ticket size
- Top POS products
- Custom order deposits

### Printing

- Print hours by printer
- Failure count by printer
- Failure reasons
- Material usage
- Jobs completed
- Jobs queued

### Inventory

- Low stock
- Dead stock
- Inventory value
- Quantity by location
- Suggested reprints

### Expenses

- Expenses by category
- Monthly trend
- Booth fees
- Filament spend
- Packaging spend
- Profit after expenses

## 13. CSV Import/Export

Exports:

- Products
- Variants
- Inventory
- Filament
- Print jobs
- Customers
- Orders
- Custom requests
- Markets
- POS sales
- Expenses

Imports:

- Products
- Variants
- Filament spools
- Inventory adjustments
- Customers

Imports should validate before writing and show errors clearly.

## 14. File Uploads

Uses:

- Product images
- Custom request reference images
- License proof
- Receipt images

Rules:

- Safe filenames
- Extension validation
- File size limits
- Admin-only access for sensitive uploads
- Do not execute uploaded files

Allowed extensions:

- jpg
- jpeg
- png
- webp
- pdf
- stl
- 3mf
- zip only if safely handled

## 15. Build Phases

### Phase 1: Foundation

- Flask factory
- Config
- Extensions
- MariaDB
- Flask-Migrate
- Flask-Login
- CSRF
- Base layout
- Tailwind
- Docker
- README
- `.env.example`
- Public home
- Login/logout
- User model
- Role field
- Dashboard shell
- Seed admin command
- Smoke tests

### Phase 2: Catalog and Fleet

- Categories
- Collections
- Products
- Variants
- Model assets/licenses
- Printers
- AMS units
- Filament spools
- Inventory locations
- Inventory records
- Admin CRUD
- API endpoints
- Demo seed data

### Phase 3: Orders, Custom Requests, Print Jobs

- Customers
- Public custom order form
- Custom order workflow
- Orders
- Order items
- Payments
- Print jobs
- Print queue
- Inventory adjustments
- Convert custom request to order
- Create print job from order item

### Phase 4: POS

- POS sessions
- POS sale screen
- Product tile buttons
- Cart
- Cash checkout
- External card placeholder
- Other payments
- Custom item
- Custom order deposit
- Customer quick create
- Receipt page
- Inventory deduction
- Market attribution
- Session close summary
- POS API
- POS tests

### Phase 5: Markets and Expenses

- Vendor markets
- Packing lists
- Market sales
- Market performance review
- Expenses
- CSV exports
- API endpoints

### Phase 6: Analytics and Polish

- Executive analytics
- Product analytics
- Market analytics
- POS analytics
- Printing analytics
- Inventory analytics
- Expense analytics
- Chart.js charts
- Public site polish
- SEO basics
- Error pages
- API docs
- Final tests
- Deployment docs

## 16. Acceptance Criteria

Initial real-use version is ready when:

- Admin can log in
- Products can be created
- Products can appear on public site and POS
- Inventory can be tracked
- Filament can be tracked
- Printers can be tracked
- Public custom requests work
- Orders can be created
- Print jobs can be created
- POS can run a cash sale on mobile
- POS deducts inventory
- POS session can close with cash summary
- Markets can be planned
- Expenses can be tracked
- Analytics summary works
- API tokens can be created
- API can read/write major resources
- CSV exports work
- Docker works
- README explains everything
