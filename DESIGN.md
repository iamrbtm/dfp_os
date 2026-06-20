# DESIGN.md

# DFPos and DudeFish Printing Design System

## 0. Purpose

This file defines the full design direction for the DudeFish Printing public website, admin pages, and DFPos internal operating system. It is meant to be used by Codex, OpenCode, or any frontend developer working on the project.

The public website screenshots from Figma Make are the visual source of truth for the brand direction. The internal DFPos app must not look like a separate random admin template. It should share the same design DNA, but adapted for speed, dense information, checkout workflows, inventory management, receipt review, market operations, analytics, and owner/admin tools.

This is not just a color palette. It is a design operating manual.

The goal is simple: DudeFish Printing should feel like one polished product from the first public landing page all the way through internal POS checkout, receipt review, inventory updates, and analytics.

## 1. Product Scope

DFPos includes two connected design surfaces.

### 1.1 Public Website

The public site is for customers. It supports:

- Product browsing
- Product purchasing
- Custom order requests
- File and image uploads for custom ideas
- Market and event discovery
- Gallery browsing
- 3D printing education
- Contact forms
- FAQ and policies
- Cart and checkout
- Order lookup if implemented later

The public site should feel welcoming, creative, modern, family-run, and trustworthy.

### 1.2 Admin and DFPos Internal App

The admin and internal app are for the business owner, helpers, cashiers, and market staff. They support:

- Fast POS checkout
- Market sales mode
- Inventory management
- Product management
- Custom order management
- Receipt intake and review
- Cost tracking
- Market expenses and revenue tracking
- Analytics
- Prep tasks
- Customer and order lookup
- Settings
- Audit log visibility
- Public website content management

The internal app should feel fast, calm, practical, clear, and reliable. It needs to work when someone is tired at a market, using a tablet, dealing with a line of customers, or trying to enter receipt data late at night. Cute is optional. Usable is not.

## 2. Design Source and Visual Direction

Use the Figma Make public website screenshots as the style source. They show a strong design direction:

- Warm off-white page backgrounds
- Clean centered page layouts
- Rounded cards
- Soft borders
- Large readable headings
- Friendly product cards
- Coral-orange primary actions
- Teal secondary actions
- Deep navy hero sections
- Dark footer and dark utility sections
- Light, open spacing
- Pill navigation states
- Soft peach active nav backgrounds
- Calm form cards
- Step-by-step custom order flow
- Minimal but meaningful icon use
- High contrast between content areas and calls to action

The public design is airy and customer-friendly. The admin side should use the same colors, radius, shadows, inputs, typography, and interaction states, but with a more compact, work-focused layout.

Do not copy the Figma pages blindly. Some Figma content is placeholder content and should not become business truth. For example, do not hardcode example locations, fake people, fake policies, fake testimonials, fake customer counts, fake reviews, fake shipping rules, fake emails, or fake market names.

## 3. Brand Personality

DudeFish Printing should feel like a serious small business that still has a pulse. The design should say:

- We make fun things.
- We know what we are doing.
- We are real people.
- Ordering is not scary.
- Custom work is welcome.
- The business is active and organized.
- Your order will not disappear into the void.

Avoid sterile corporate SaaS design. Avoid loud hobby-store chaos. The sweet spot is warm, clean, useful, and a little playful.

### 3.1 Public Emotion

When a customer lands on the public site, they should quickly understand:

- What DudeFish Printing sells
- How to shop
- How to request something custom
- Where to find the business in person
- Why the business is trustworthy
- What 3D printing means in plain English

The visitor should feel comfortable, not dumb. Many customers will not know what STL, PLA, FDM, slicer, supports, or infill mean. The website should translate the business without talking down to people.

### 3.2 Internal Emotion

When the owner or staff opens DFPos, they should feel:

- In control
- Not overwhelmed
- Confident about checkout
- Able to find the right module quickly
- Able to trust the numbers
- Able to recover from mistakes
- Able to review what happened later through audit logs

The internal app should reduce mental load. Every screen should make the next action obvious.

## 4. Design Principles

### 4.1 One Brand, Two Modes

Public pages and admin pages must feel related. Use the same tokens, typography, radius, button treatment, input style, card style, badge style, and icon style.

Public pages can be more spacious and story-driven. Admin pages should be denser and task-driven.

### 4.2 Speed Beats Decoration

Animations, gradients, and visual flourishes are allowed only when they help orientation, trust, or comprehension. Nothing should slow down POS checkout, product browsing, receipt review, or form submission.

### 4.3 Clear Hierarchy

Every page needs one obvious main action. Secondary actions must look secondary. Destructive actions must be visually distinct and must usually require confirmation.

### 4.4 No Mystery Meat UI

Buttons must say what they do. Icons need labels unless the meaning is obvious and repeated everywhere, like cart, search, close, or settings.

### 4.5 Data Must Be Scannable

Admin screens must use compact rows, clear status badges, readable numbers, sticky table headers where useful, and predictable filters.

### 4.6 Mobile Is Real

Public pages must work beautifully on phones. Admin pages must support tablets and laptops first, with mobile access for quick lookups, market mode, and urgent edits.

### 4.7 Never Fake Business Reality

Do not create fake testimonials, fake reviews, fake market locations, fake customer counts, fake product counts, fake policies, or fake analytics. Use empty states, sample dev seed data clearly marked as development-only, or placeholders that tell the developer exactly what real data is needed.

## 5. Core Layout System

### 5.1 Page Widths

Use a consistent max-width system.

- Marketing/public content container: `max-width: 1120px`
- Narrow article/form container: `max-width: 760px`
- Product grid container: `max-width: 1180px`
- Admin app full width: fluid with `24px` desktop padding
- Admin dense pages: use full width with clear card grouping
- POS mode: full viewport layout, optimized for speed

### 5.2 Spacing Scale

Use a 4px-based spacing scale.

```css
--space-1: 4px;
--space-2: 8px;
--space-3: 12px;
--space-4: 16px;
--space-5: 20px;
--space-6: 24px;
--space-8: 32px;
--space-10: 40px;
--space-12: 48px;
--space-16: 64px;
--space-20: 80px;
--space-24: 96px;
```

Public pages can use larger spacing. Admin pages should use tighter spacing.

Recommended vertical spacing:

- Public hero top/bottom: `72px` to `96px`
- Public section gap: `64px` to `88px`
- Admin page header to content: `20px` to `28px`
- Admin card internal padding: `16px` to `24px`
- Data table row height: `48px` to `56px`
- POS product tile gap: `12px` to `16px`

### 5.3 Border Radius

The screenshots use friendly rounded shapes. Keep that.

```css
--radius-xs: 6px;
--radius-sm: 10px;
--radius-md: 14px;
--radius-lg: 18px;
--radius-xl: 24px;
--radius-full: 999px;
```

Usage:

- Buttons: `--radius-full` or `--radius-md`
- Product cards: `--radius-md`
- Form cards: `--radius-lg`
- Inputs: `--radius-md`
- Badges and nav pills: `--radius-full`
- Dashboard cards: `--radius-lg`
- Modals and drawers: `--radius-xl`

Do not use sharp square boxes unless the design specifically calls for dense data tables.

### 5.4 Shadows

Use soft depth, not heavy drop shadows.

```css
--shadow-xs: 0 1px 2px rgb(15 23 42 / 0.05);
--shadow-sm: 0 2px 8px rgb(15 23 42 / 0.06);
--shadow-md: 0 8px 24px rgb(15 23 42 / 0.08);
--shadow-lg: 0 16px 40px rgb(15 23 42 / 0.12);
```

Usage:

- Default cards: no shadow or `--shadow-xs`
- Active cards/drawers: `--shadow-sm`
- Modals: `--shadow-lg`
- Admin dense tables: prefer borders over shadows

## 6. Color System

All colors must use design tokens. Do not hardcode colors inside templates, components, or scripts.

The Figma direction uses warm off-white backgrounds, coral-orange primary action, teal secondary action, deep navy hero areas, and near-black dark footer/app sections.

### 6.1 Light Theme Tokens

```css
:root,
[data-theme="light"] {
  --color-bg-page: #f9f9f6;
  --color-bg-section: #f4f7f4;
  --color-bg-surface: #ffffff;
  --color-bg-surface-soft: #f7f7f5;
  --color-bg-elevated: #ffffff;

  --color-border: #e4e2dd;
  --color-border-strong: #cbc7bf;
  --color-border-subtle: #efede8;

  --color-text-primary: #18191d;
  --color-text-secondary: #5f626b;
  --color-text-muted: #8a8d96;
  --color-text-inverse: #ffffff;

  --color-primary: #ef5a28;
  --color-primary-hover: #d94d20;
  --color-primary-active: #bd421b;
  --color-primary-soft: #fde9e1;
  --color-primary-soft-hover: #fbd7c9;

  --color-secondary: #08b8ac;
  --color-secondary-hover: #079e95;
  --color-secondary-active: #057f78;
  --color-secondary-soft: #ddf8f5;
  --color-secondary-soft-hover: #c5f2ee;

  --color-accent-navy: #1b2650;
  --color-accent-navy-hover: #162044;
  --color-accent-navy-soft: #e7eaf5;

  --color-success: #16a34a;
  --color-success-soft: #dcfce7;
  --color-warning: #f59e0b;
  --color-warning-soft: #fef3c7;
  --color-danger: #dc2626;
  --color-danger-soft: #fee2e2;
  --color-info: #0284c7;
  --color-info-soft: #e0f2fe;

  --color-input-bg: #f4f3ef;
  --color-input-border: #d9d6cf;
  --color-input-placeholder: #92918b;
  --color-focus-ring: #08b8ac;

  --color-badge-sale-bg: #ef5a28;
  --color-badge-sale-text: #ffffff;
  --color-badge-custom-bg: #08b8ac;
  --color-badge-custom-text: #ffffff;
  --color-badge-event-bg: #ddf8f5;
  --color-badge-event-text: #057f78;

  --color-footer-bg: #18191d;
  --color-footer-border: #2a2b31;
  --color-footer-text: #f5f5f3;
  --color-footer-muted: #a4a7ad;
}
```

### 6.2 Dark Theme Tokens

Dark mode is recommended for DFPos admin, especially for market checkout and late-night review work. The public site can have dark sections without requiring full public dark mode at launch.

```css
[data-theme="dark"] {
  --color-bg-page: #101115;
  --color-bg-section: #15171c;
  --color-bg-surface: #18191d;
  --color-bg-surface-soft: #202229;
  --color-bg-elevated: #24262e;

  --color-border: #30323a;
  --color-border-strong: #444852;
  --color-border-subtle: #252730;

  --color-text-primary: #f9f9f6;
  --color-text-secondary: #c9cbd1;
  --color-text-muted: #8f939e;
  --color-text-inverse: #18191d;

  --color-primary: #ff6a35;
  --color-primary-hover: #ef5a28;
  --color-primary-active: #d94d20;
  --color-primary-soft: #3a2119;
  --color-primary-soft-hover: #4a281d;

  --color-secondary: #14cfc3;
  --color-secondary-hover: #08b8ac;
  --color-secondary-active: #079e95;
  --color-secondary-soft: #123532;
  --color-secondary-soft-hover: #16433f;

  --color-accent-navy: #223166;
  --color-accent-navy-hover: #2b3d7d;
  --color-accent-navy-soft: #171d34;

  --color-success: #22c55e;
  --color-success-soft: #12351f;
  --color-warning: #fbbf24;
  --color-warning-soft: #3f3010;
  --color-danger: #f87171;
  --color-danger-soft: #3b1717;
  --color-info: #38bdf8;
  --color-info-soft: #102f3f;

  --color-input-bg: #202229;
  --color-input-border: #3a3d46;
  --color-input-placeholder: #8f939e;
  --color-focus-ring: #14cfc3;

  --color-badge-sale-bg: #ff6a35;
  --color-badge-sale-text: #18191d;
  --color-badge-custom-bg: #14cfc3;
  --color-badge-custom-text: #101115;
  --color-badge-event-bg: #123532;
  --color-badge-event-text: #8af3ea;

  --color-footer-bg: #101115;
  --color-footer-border: #252730;
  --color-footer-text: #f9f9f6;
  --color-footer-muted: #a4a7ad;
}
```

### 6.3 Color Usage Rules

- Use coral-orange for primary purchase, submit, save, and checkout actions.
- Use teal for custom order, support, informational, and helpful secondary actions.
- Use navy for high-impact hero sections, market callouts, and admin focus panels.
- Use off-white backgrounds to avoid sterile white dashboards.
- Use dark near-black for footers and optional admin sidebars.
- Use semantic colors only for their meaning. Do not make a random warning badge green because it looks nice.
- Never rely on color alone. Pair status color with text and icons.

## 7. Typography

The screenshots use bold, rounded, modern typography. The implementation should use a clean sans-serif with friendly geometry.

Recommended stack:

```css
--font-sans: Inter, Nunito Sans, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
--font-mono: "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
```

If only system fonts are used, the app should still look good.

### 7.1 Type Scale

```css
--text-xs: 12px;
--text-sm: 14px;
--text-md: 16px;
--text-lg: 18px;
--text-xl: 20px;
--text-2xl: 24px;
--text-3xl: 32px;
--text-4xl: 44px;
--text-5xl: 56px;
```

### 7.2 Font Weights

```css
--font-regular: 400;
--font-medium: 500;
--font-semibold: 600;
--font-bold: 700;
--font-extrabold: 800;
```

### 7.3 Typography Rules

- Public hero headings should be large, bold, and warm.
- Admin page headings should be smaller and functional.
- Use sentence case for buttons and labels unless a product name requires otherwise.
- Use all-caps only for tiny category labels, table column headers, and small metadata tags.
- Body text should be readable at `16px` on public pages.
- Admin tables may use `14px`, but never below `12px` for important information.
- Numeric values in POS, analytics, and cost screens should use tabular numbers where available.

## 8. Icon System

Use one consistent icon family across public and admin pages. Lucide-style line icons are a good match.

Icon rules:

- Stroke width should feel light but readable, around `1.75px` to `2px`.
- Pair icons with labels in navigation and admin actions.
- Public category icons can be simple and friendly.
- Admin icons should be practical: cart, inventory, receipt, chart, calendar, customer, settings, audit, alert.
- Icon-only buttons must have accessible labels.
- Do not mix chunky filled icons with thin line icons unless it is a status badge or logo.

## 9. Public Website Architecture

The public website should include these routes.

| Route | Page | Purpose |
|---|---|---|
| `/` | Home | Explain the business, sell products, push custom orders, show markets, build trust. |
| `/shop` | Shop | Browse ready-made products with filters, search, sorting, and cart actions. |
| `/shop/:slug` | Product Detail | Product photos, options, price, dimensions, materials, care, add to cart. |
| `/custom-orders` | Custom Order Wizard | Friendly multi-step intake for custom work. |
| `/markets` | Markets & Events | Upcoming event list, booth info, directions, event notes. |
| `/gallery` | Gallery | Past work, inspiration, custom examples, request similar behavior. |
| `/about` | About | Real story, values, quality, family-run tone. |
| `/learn` | Learn 3D Printing | Plain-English 3D printing education. |
| `/materials` | Materials & Options | PLA, PETG, colors, finish, limits, care. |
| `/faq` | FAQ & Policies | FAQ accordions and policy summaries. |
| `/contact` | Contact | Contact methods, topic form, custom order routing. |
| `/cart` | Cart | Cart detail, quantity changes, shipping or pickup prompt. |
| `/checkout` | Checkout | Secure checkout through trusted provider. |
| `/order-lookup` | Order Lookup | Optional customer-facing status lookup. |

### 9.1 Public Header

The public header should match the Figma direction:

- White or off-white sticky header
- Logo on the left
- Center or right aligned nav links
- Active nav shown as soft peach pill
- Teal `Custom Order` button
- Cart icon with item count
- Mobile hamburger menu

Desktop nav order:

1. Shop
2. Custom Orders
3. Markets & Events
4. Gallery
5. About
6. Learn
7. FAQ
8. Contact
9. Custom Order CTA
10. Cart

Mobile nav:

- Logo left, cart and menu right
- Slide-down or drawer menu
- Large tap targets
- Put `Shop` and `Start Custom Order` at the top
- Show cart summary if cart has items

### 9.2 Public Footer

Use the dark footer style from the screenshots.

Footer columns:

- Brand block with logo, short description, social icons
- Shop links
- Info links
- Legal links
- Contact/location summary

Footer rules:

- Do not hardcode fake location or email values.
- Pull contact information from settings/CMS.
- Keep footer text muted but readable.
- Use clear legal links.

## 10. Public Homepage Design

The homepage should follow the visual rhythm shown in the Figma screenshot.

### 10.1 Hero Section

Use a deep navy hero with warm orange and teal accents.

Hero content:

- Small pill: `Family-run 3D printing` or current local positioning
- Large headline with one orange-highlight phrase
- Short explanation of what DudeFish sells
- Primary button: `Shop Now`
- Secondary button: `Request Custom`
- Trust bullets below buttons
- Product image collage on the right
- Subtle abstract background circles or small dot details

Rules:

- Do not let decorative shapes compete with content.
- Product images should be real product photos once available.
- Avoid fake trust numbers unless the real system has them.

### 10.2 Category Strip

Show friendly category cards:

- Home & Decor
- Toys & Games
- Planters & Garden
- Cosplay & Props
- Functional Parts

Cards should be rounded, white, bordered, with small icon or product thumbnail.

### 10.3 Popular Picks

Use 4 to 8 product cards. The card design should match the shop page.

Required card info:

- Product image
- Category label
- Product name
- Rating only if real reviews exist
- Price
- Badge for `Custom`, `Sale`, or `Out of Stock`
- Add to cart button

No fake reviews. If reviews are not implemented, leave ratings out.

### 10.4 Custom Orders Explainer

Show a 4-step horizontal flow on desktop and vertical flow on mobile:

1. Describe your idea
2. We send a quote
3. We print it
4. Pickup or delivery

CTA: `Start a Custom Order`

### 10.5 Market Feature Section

Use a navy background block, matching the Figma homepage. Include:

- Next upcoming market
- Date/time
- Location
- Short note
- CTA: `See All Events`
- Secondary: `Get Directions`
- Event image

If no upcoming markets exist, show a friendly empty state and invite customers to follow updates.

### 10.6 Gallery Preview

Use a masonry or grid preview with 6 to 8 images. Include `View Gallery`.

Gallery items should support hover overlay with:

- Title
- Category
- `Request something like this`

### 10.7 About Preview

Use image-left/text-right layout. Keep copy real and warm.

CTA: `Meet the Team` or `About DudeFish`.

### 10.8 Trust Strip

Use small icon/value blocks:

- Quality checked
- Custom requests welcome
- Local market pickup
- Secure checkout

Only include claims that are true.

### 10.9 Final CTA

Use a full-width coral-orange section:

- Headline: `Have a question or idea?`
- Buttons: `Send a Message`, `Start Custom Order`

## 11. Public Shop Design

### 11.1 Shop Layout

The shop page should use:

- Page title and short helper text
- Search bar
- Sort dropdown
- Category pills
- Product count
- Responsive product grid
- CTA panel for custom orders at the bottom

Grid:

- Desktop: 4 columns
- Laptop: 3 columns
- Tablet: 2 columns
- Mobile: 1 column or 2 compact columns if product photos still work

### 11.2 Product Card

Product card anatomy:

- Image block with fixed aspect ratio
- Top-left badges for `Custom`, `Sale`, `Out of Stock`
- Category label
- Product name
- Optional rating if real
- Price
- Compare-at price if on sale
- Add to cart button

Card behavior:

- Entire card image/title links to product detail
- Add to cart does not navigate away
- Out-of-stock cards disable purchase button and show clear status
- Hover on desktop raises card slightly or changes border
- Touch devices should not rely on hover-only content

### 11.3 Product Detail Page

Product detail layout:

- Left: image gallery
- Right: product info and purchase panel
- Breadcrumb above
- Product title
- Price
- Availability
- Options: color, material, size, personalization fields if applicable
- Quantity
- Add to cart
- Custom request CTA if personalization is more complex
- Processing time
- Pickup/shipping notes
- Care instructions
- Safety notes where needed
- Related products

Do not bury care, size, or material information. Customers need this before buying.

## 12. Public Custom Order Flow

The Figma screenshots show a strong three-step custom order flow. Keep this pattern.

### 12.1 Wizard Steps

Steps:

1. Your Idea
2. Details
3. Contact
4. Confirmation

The step indicator should use:

- Coral for active step
- Teal with checkmark for completed steps
- Muted gray for upcoming steps
- Thin connecting lines

### 12.2 Step 1: Your Idea

Fields:

- Description textarea, required
- File upload, optional but encouraged
- Accepted file types: JPG, PNG, PDF, STL, OBJ, 3MF
- File size limit displayed clearly

Helper copy:

- `A rough description is totally fine. The more detail the better, but do not worry about getting it perfect.`
- `Upload a photo, sketch, screenshot, or 3D file if you have one.`

### 12.3 Step 2: Details

Fields:

- Approximate size
- Quantity
- Color preference
- Material preference
- Deadline if any
- Budget range
- Pickup or shipping preference

Use card-like choice buttons for pickup/shipping. Active state should use primary border and soft primary background.

### 12.4 Step 3: Contact

Fields:

- Name
- Email
- Phone optional
- Extra notes
- Consent checkbox

Show reassurance text:

- `No payment is required now. We send a quote for your approval before anything is printed.`

### 12.5 Confirmation

Use a centered success layout:

- Teal success icon in soft teal circle
- Heading: `Request Received`
- Short message with expected response time from business settings
- Button: `Submit Another Request`
- Optional button: `Back to Shop`

Do not promise a response time unless it is configured.

## 13. Public Markets and Events

Use large event cards like the Figma screenshot.

Event card anatomy:

- Event image
- Event name
- Recurring badge if applicable
- Date
- Time
- Location
- Short description
- `Find us` booth/table info callout
- `Get Directions` link

Rules:

- Pull events from DFPos/admin.
- Support no-events empty state.
- Past events may be archived and used in gallery.
- Directions links should open maps in a new tab.
- Do not expose private admin notes.

## 14. Public Gallery

Use filter pills and a square image grid.

Categories:

- Home & Decor
- Toys & Games
- Planters & Garden
- Cosplay & Props
- Functional Parts
- Market Booth
- Behind the Scenes

Gallery item behavior:

- Click opens detail modal or page
- Show title, category, and optional product link
- Support `Request something like this`
- If an item links to a product, use `Shop This Item`

Images should use real work, real market photos, or clearly marked placeholders during development.

## 15. Public Learn and FAQ Pages

Use accordions like the Figma screenshots.

### 15.1 Learn Page

Topics:

- What is 3D printing?
- What can be printed?
- What materials are used?
- What are print lines?
- How long does printing take?
- What colors are available?
- How durable are prints?
- How do I care for my print?
- Tips for a first custom order

The copy should be written for regular customers. No jargon dumps.

### 15.2 FAQ Page

Use category filter pills:

- All
- Ordering
- Materials
- Shipping & Pickup
- Returns & Issues
- Custom Orders
- Privacy & Security

FAQ cards below should summarize policies but must not invent legal promises.

## 16. Public Contact Page

Use two-column layout on desktop.

Left column:

- Contact methods
- Social links
- Service area if configured
- Custom order CTA card

Right column:

- Contact form card
- Name
- Email
- Topic dropdown
- Message
- Privacy note
- Send button

Topic options:

- General question
- Custom order question
- Existing order
- Market/event question
- Product question
- Website issue

Security:

- Spam protection
- Rate limiting
- Server-side validation
- No sensitive data in frontend code

## 17. Admin and DFPos App Architecture

The admin area and DFPos app should be available under routes such as:

| Route | Module | Purpose |
|---|---|---|
| `/admin` | Admin Dashboard | Business summary and quick actions. |
| `/admin/pos` | POS | Fast checkout for markets, cash, and later card processing. |
| `/admin/orders` | Orders | Public, POS, custom, and manual orders. |
| `/admin/custom-orders` | Custom Orders | Quote review, files, customer communication, status. |
| `/admin/products` | Products | Product catalog and public shop management. |
| `/admin/inventory` | Inventory | Stock counts, materials, filament, finished goods. |
| `/admin/markets` | Markets | Events, sales, fees, prep lists, financial results. |
| `/admin/receipts` | Receipts | Receipt upload, AI/manual review, line categorization. |
| `/admin/analytics` | Analytics | Sales, profit, markets, products, costs, trends. |
| `/admin/prep` | Prep Tasks | Tasks for markets, orders, printing, packing. |
| `/admin/customers` | Customers | Customer lookup and order history. |
| `/admin/settings` | Settings | Business, tax, payment, theme, users, integrations. |
| `/admin/audit-log` | Audit Log | Human-readable audit trail from audit microservice. |
| `/admin/site-content` | Site Content | Homepage, FAQ, events, gallery, policies, announcements. |

### 17.1 Admin Shell

Desktop admin shell:

- Left sidebar navigation
- Top bar with page title, search, quick actions, user menu
- Main content area
- Optional right detail drawer for selected items

Tablet admin shell:

- Collapsible sidebar
- Bottom or top quick actions for POS
- Larger tap targets

Mobile admin shell:

- Bottom nav for common actions: Dashboard, POS, Orders, Inventory, More
- Most dense admin editing should show a warning if mobile layout is limited
- Quick lookup and market actions must still be usable

### 17.2 Admin Sidebar

Sidebar sections:

- Sell: POS, Orders, Custom Orders
- Manage: Products, Inventory, Markets, Receipts, Prep
- Understand: Analytics, Audit Log
- Configure: Site Content, Settings

Use icons plus labels. Active item should use soft primary background and primary text or a left border accent.

### 17.3 Admin Page Header

Every admin page should have:

- Page title
- Short one-line description
- Primary action button
- Secondary action menu if needed
- Optional breadcrumbs
- Optional saved view/filter controls

Example:

```text
Inventory
Track finished products, materials, filament, and low-stock items.
[Add Item] [Import] [More]
```

## 18. Admin Dashboard Design

The dashboard should answer: what needs attention right now?

Sections:

1. Today summary cards
2. Open tasks and alerts
3. Recent orders
4. Upcoming markets
5. Low inventory
6. Receipt review queue
7. Sales trend
8. Quick actions

### 18.1 Summary Cards

Cards:

- Today sales
- Open custom orders
- Items low stock
- Receipts needing review
- Upcoming market countdown
- Pending prep tasks

Use clear numbers, small labels, trend indicators, and links to the relevant module.

### 18.2 Alerts

Alert examples:

- `3 receipts need review`
- `12 products below reorder point`
- `Market prep list due tomorrow`
- `Custom order quote waiting 3 days`

Alerts should be actionable. Every alert needs a button or link.

## 19. POS Design

The POS is the most time-sensitive internal screen. It must be fast.

### 19.1 POS Layout

Desktop/tablet POS layout:

- Left: product search, category tabs, product tile grid
- Right: cart/order panel
- Top: market selector, sale mode, customer optional, sync status
- Bottom or sticky area: payment actions

### 19.2 Product Tiles

Product tile anatomy:

- Product image or colored icon fallback
- Product name
- Price
- Stock count or market quantity
- Badge for custom, sale, low stock, sold out

Tiles must be large enough for touch. Minimum target: `44px`, preferred POS tile height: `96px` to `132px`.

### 19.3 POS Cart Panel

Cart row:

- Product name
- Variant
- Quantity controls
- Price
- Remove button

Cart summary:

- Subtotal
- Discount
- Tax
- Fees
- Total
- Payment method buttons
- Complete sale button

Payment methods:

- Cash
- Card placeholder/provider
- Venmo
- Cash App
- Apple Pay/manual external if used
- Other/manual

The app must clearly show when payment was recorded externally versus processed inside the system.

### 19.4 POS Error Prevention

- Confirm refunds and voids.
- Make quantity changes obvious.
- Warn when stock would go negative.
- Allow held carts if implemented.
- Support quick undo for removing cart items.
- Log every sale, refund, void, discount, inventory adjustment, and payment method change to audit service.

## 20. Product and Inventory Admin Design

### 20.1 Products

Products module should support:

- Public product status
- POS availability
- Market availability
- Photos
- Categories
- Variants
- Pricing
- Cost estimate
- Materials
- Print time
- Stock
- Customizable flag
- SEO fields for public site

Product list table columns:

- Image
- Name
- Category
- Price
- Stock
- Public status
- POS status
- Updated
- Actions

Use filters:

- Active
- Draft
- Public
- POS only
- Low stock
- Out of stock
- Customizable

### 20.2 Inventory

Inventory module should separate:

- Finished goods
- Filament/materials
- Packaging supplies
- Market bins
- Custom order materials

Inventory item card/list should show:

- Item name
- Type
- Current quantity
- Reorder point
- Cost
- Location/bin
- Last change
- Status

Inventory status badges:

- In Stock
- Low Stock
- Out of Stock
- Needs Count
- Reserved
- Market Packed

All inventory changes must be logged.

## 21. Custom Orders Admin Design

Custom orders should use a pipeline board plus list view.

Statuses:

- New Request
- Needs Review
- Quote Needed
- Quote Sent
- Approved
- In Design
- Printing
- Post Processing
- Ready for Pickup
- Shipped/Completed
- Cancelled

### 21.1 Custom Order Detail

Detail page or drawer should include:

- Customer info
- Request description
- Uploaded files
- Images
- Size, quantity, color, material, deadline
- Budget
- Pickup/shipping preference
- Internal notes
- Quote builder
- Cost estimate
- Tasks
- Communication timeline
- Status history
- Audit history link

Use tabs if needed:

- Overview
- Files
- Quote
- Tasks
- Messages
- Audit

### 21.2 Quote UI

Quote builder should show:

- Materials cost
- Print time
- Labor/design time
- Machine time
- Packaging
- Shipping/pickup
- Discount
- Tax
- Total quote

The quote screen should make assumptions visible. No hidden math nonsense.

## 22. Receipt Intake and Review Design

Receipt intake replaces the old expenses module.

### 22.1 Receipt Sources

Support:

- Upload file/image
- Camera capture
- Email forwarding if implemented
- Manual entry fallback

### 22.2 Receipt Review Layout

Use a two-panel review screen:

- Left: receipt image/PDF viewer
- Right: extracted metadata and line items

Metadata fields:

- Store/vendor
- Date/time
- Receipt number
- Payment method
- Subtotal
- Tax
- Fees
- Total
- Confidence score

Line item table:

- Description
- Quantity
- Unit price
- Total
- Category
- Assign to inventory, market, custom order, or business expense
- Tax/fee allocation
- Confidence
- Review status

### 22.3 Review States

Statuses:

- Uploaded
- Extracting
- Needs Review
- Reviewed
- Posted
- Error

The UI must make it obvious when AI extraction is uncertain. Confidence badges should use clear text, not just color.

### 22.4 Inventory Prompt

If a receipt line looks like inventory, the UI should offer:

- Create new inventory item
- Add stock to existing item
- Assign cost to material
- Ignore for inventory

This should open a side drawer, not kick the user out of receipt review.

## 23. Markets Module Design

Markets are core to DudeFish Printing. The module must connect public events, POS, inventory, prep, and analytics.

### 23.1 Market List

Market cards/table should show:

- Market name
- Date/time
- Location
- Booth/table info
- Status
- Expected inventory
- Prep progress
- Revenue after event
- Expenses/fees
- Profit estimate

Statuses:

- Draft
- Scheduled
- Prep Needed
- Packed
- Active
- Completed
- Cancelled

### 23.2 Market Detail

Tabs:

- Overview
- Prep List
- Inventory
- Sales
- Expenses
- Public Listing
- Notes
- Analytics

### 23.3 Market Prep

Prep checklist:

- Products to print
- Products to pack
- Display supplies
- Payment supplies
- Signage/QR codes
- Cash box
- Weather/location notes
- Special items

Use progress bars and due dates. This needs to help in real life, not just sit there looking organized.

### 23.4 Public Event Sync

Admin event fields that can publish to public site:

- Public title
- Date/time
- Public location
- Directions link
- Booth/table info
- Description
- Featured products
- Event image
- Visibility toggle

Private admin-only fields:

- Internal notes
- Fees
- Sales goals
- Vendor contact
- Setup instructions
- Profit calculations

Never expose private fields on the public site.

## 24. Analytics Design

Analytics should be useful, not dashboard confetti.

### 24.1 Analytics Overview

Sections:

- Sales over time
- Revenue by channel
- Profit estimate
- Top products
- Top categories
- Market performance
- Custom order pipeline
- Inventory value
- Expense trends from receipts

### 24.2 Chart Rules

- Use clear labels.
- Never use tiny unreadable legends.
- Always show empty/loading/error states.
- Use tooltips for details.
- Use accessible colors and patterns where possible.
- Use date range filters.
- Let users export CSV where useful.

### 24.3 AI Analytics Notes

If ChatGPT or another model is used for analytics summaries, label generated insights clearly. The model should summarize the numbers, not invent meaning that data does not support.

Example:

```text
AI summary based on sales and receipt data from Jan 1 to Jan 31.
```

## 25. Audit Log Design

DFPos uses an audit logging microservice. The design must support audit visibility without making normal users feel like they are in a courtroom.

### 25.1 Audit Events to Log

Log every important action, including:

- Sale created
- Sale voided
- Refund issued
- Payment method changed
- Inventory adjusted
- Product changed
- Receipt uploaded
- Receipt edited
- Receipt posted
- Market financial change
- Custom order status change
- Quote sent
- User login/logout
- User permission change
- Settings change
- Public content published/unpublished
- File uploaded/deleted

### 25.2 Audit Log UI

Audit table columns:

- Timestamp
- User
- Action
- Module
- Entity
- Summary
- IP/device if available
- Risk/severity
- Details action

Filters:

- Date range
- User
- Module
- Action type
- Severity
- Entity ID

Detail view:

- Before/after values
- Request metadata
- Related record links
- Correlation ID
- Raw event JSON behind a developer-only disclosure

Use neutral language. `Inventory count changed from 12 to 9` is better than `User tampered with stock`.

## 26. Site Content Admin Design

The admin must allow the owner to update public content without code.

Manageable content:

- Homepage hero copy
- Featured products
- Categories
- Market/event listings
- Gallery images
- Learn articles
- FAQ entries
- Policy pages
- Announcements
- Contact info
- Social links
- Footer text
- Sale banners
- Custom order examples

### 26.1 Publish Workflow

For public content editing:

- Draft state
- Preview
- Publish
- Unpublish
- Last edited by
- Last published date
- Audit entry

Never publish accidental placeholder content without an explicit action.

## 27. Component Library

All components must be reusable across public and admin unless there is a strong reason not to.

### 27.1 Button

Variants:

- Primary
- Secondary
- Ghost
- Outline
- Danger
- Link
- Icon

Sizes:

- Small
- Medium
- Large
- POS large

Rules:

- Primary button uses coral.
- Secondary button uses teal.
- Danger uses red.
- Disabled buttons must have clear disabled styling and not only reduced opacity.
- Loading buttons should show spinner and keep layout stable.

### 27.2 Card

Variants:

- Standard
- Product
- Metric
- Event
- Form
- Alert
- POS tile
- Admin row card

Rules:

- Use soft border and rounded corners.
- Use hover affordance only for clickable cards.
- Avoid nesting too many cards inside cards.

### 27.3 Badge or Status Pill

Variants:

- Sale
- Custom
- Event
- Success
- Warning
- Danger
- Info
- Neutral
- Draft
- Active
- Completed
- Needs Review

Badges must include text. Color alone is not enough.

### 27.4 Forms

Form style should match the custom order screenshots:

- Rounded input backgrounds
- Clear labels
- Required marker
- Helper text
- Error text under field
- Strong focus ring
- Grouped card sections

Rules:

- Labels are required.
- Placeholders are examples, not labels.
- Validation happens client-side and server-side.
- Required fields are clear.
- Long forms should be split into steps.

### 27.5 File Upload

Use a dashed drop zone with icon, label, allowed file types, max size, and upload state.

States:

- Empty
- Dragging
- Uploading
- Uploaded
- Failed
- Invalid type
- Too large
- Virus scan pending if implemented

### 27.6 Data Table

Used for admin lists.

Features:

- Search
- Filters
- Sort
- Pagination
- Bulk actions
- Row actions
- Sticky header for long tables
- Empty state
- Loading skeleton
- Error retry

Rules:

- Keep columns focused.
- Use drawers for detail instead of making every row huge.
- Bulk destructive actions need confirmation.

### 27.7 Drawer

Use drawers for carts, detail previews, quick edits, and receipt inventory prompts.

Rules:

- Right drawer for desktop.
- Full-screen sheet on mobile.
- Trap focus when open.
- Escape closes unless there are unsaved changes.
- Unsaved changes require confirmation.

### 27.8 Modal

Use modals for focused confirmations, not full workflows.

Good modal uses:

- Delete confirmation
- Refund confirmation
- Void sale confirmation
- Publish confirmation
- Quick info display

Bad modal uses:

- Full product editing
- Long receipt review
- Complex analytics filters

### 27.9 Toasts and Alerts

Toast rules:

- Use toasts for quick non-blocking confirmation.
- Use inline alerts for important information that affects workflow.
- Error toasts should include what failed and what to do next.

### 27.10 Empty States

Every empty state should explain:

- What is empty
- Why it matters
- What to do next

Examples:

- `No products yet. Add your first product to start selling online and in POS.`
- `No receipts need review. Nice. Enjoy the rare silence.`
- `No upcoming markets. Add one to show customers where to find you.`

## 28. Required States

Every dynamic component and page must include:

- Loading state
- Empty state
- Error state
- Success state
- Validation state
- Offline or unavailable state where useful
- Permission denied state
- Unsaved changes state

### 28.1 Loading

Use skeletons for lists/cards and spinners for buttons. Avoid full-page spinners unless the whole app is loading.

### 28.2 Error

Error messages must be specific.

Bad:

```text
Something went wrong.
```

Better:

```text
Receipt upload failed. Check the file type and try again.
```

### 28.3 Success

Success states should confirm the result and offer the next logical action.

Example:

```text
Product saved.
View public page or keep editing.
```

## 29. Accessibility Requirements

Accessibility is not a later patch. Build it in.

Requirements:

- WCAG-friendly contrast
- Keyboard navigation
- Visible focus states
- Proper form labels
- Error messages tied to fields
- Accessible modals and drawers
- Accessible accordions
- Skip links on public pages
- Alt text for meaningful images
- Empty alt text for decorative images
- Reduced motion support
- Large tap targets
- Plain language instructions
- Screen reader labels for icon-only buttons
- No hover-only interactions
- Tables need headers and captions where useful
- POS must support keyboard shortcuts without breaking accessibility

Focus ring:

```css
:focus-visible {
  outline: 3px solid var(--color-focus-ring);
  outline-offset: 2px;
}
```

Reduced motion:

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    scroll-behavior: auto !important;
    transition-duration: 0.01ms !important;
  }
}
```

## 30. Security Design Requirements

The public site and DFPos admin must be designed with security from the start. Duct tape security is how projects get haunted.

### 30.1 Public Website Security

- HTTPS only
- Secure checkout through trusted payment provider
- Never store raw payment card data
- Server-side form validation
- Spam protection
- Rate limiting for contact/custom order forms
- Secure file upload handling
- File type allowlist
- File size limits
- Malware scanning recommendation for uploaded files
- Private storage for uploaded custom order files
- Signed URLs for private downloads
- No secret keys in frontend code
- Privacy-respecting analytics
- Safe error messages
- Secure account handling if accounts are added

### 30.2 Admin Security

- Authentication required
- Role-based access control
- Admin-only routes protected server-side
- CSRF protection for state-changing actions
- Audit logging for every important change
- Session timeout rules
- Secure password and account recovery flow
- Environment variables for secrets
- No sensitive customer data in logs unless explicitly required and protected
- File downloads permission-checked
- Public content preview cannot expose private admin data

### 30.3 File Upload Security

For custom orders and receipts:

- Allow only approved types
- Validate MIME type and extension
- Limit file size
- Store outside public web root or in private object storage
- Generate safe filenames
- Strip dangerous metadata where possible
- Scan for malware when practical
- Never execute uploaded files
- Do not render uploaded SVG or HTML as trusted content

## 31. Performance Requirements

### 31.1 Public Site

- Fast first load
- Optimized images
- Responsive image sizes
- Lazy load below-the-fold images
- Minimal JavaScript
- Cache static assets
- Use CDN when available
- Avoid heavy animation libraries
- Keep checkout fast
- Keep custom order wizard reliable

### 31.2 Admin App

- POS must load quickly and work smoothly
- Product search should feel instant
- Receipt review should handle large images/PDFs without freezing
- Tables should paginate or virtualize when large
- Analytics should lazy load expensive charts
- Use optimistic UI carefully, only when rollback is safe
- Show sync/error states clearly

## 32. SEO and Local Discovery

Public pages need SEO. Admin pages do not.

Public SEO requirements:

- Unique page titles
- Meta descriptions
- Clean URLs
- Product schema
- Local business schema
- Event schema
- FAQ schema
- Image alt text
- Sitemap
- Robots.txt
- Social sharing previews
- Local keywords managed from settings
- Google Business Profile alignment if used

Do not index admin routes.

Admin route requirements:

```html
<meta name="robots" content="noindex,nofollow">
```

Also protect admin routes server-side. Meta tags are not security.

## 33. Responsive Rules

### 33.1 Public Desktop

- Full navigation visible
- Large hero layouts
- 4-column product grid
- 2-column forms/contact pages
- Wide gallery grids

### 33.2 Public Tablet

- Condensed nav or hamburger
- 2-column product grid
- Wizard remains centered
- Event cards can stack image and content

### 33.3 Public Mobile

- Hamburger nav
- Sticky cart if useful
- 1-column product grid or 2 compact cards if tested
- Full-width buttons
- Custom order wizard uses vertical stepper or compact step header
- Inputs are large and easy to tap
- Footer stacks columns

### 33.4 Admin Desktop

- Sidebar visible
- Dense tables
- Multi-column layouts
- Drawers for details

### 33.5 Admin Tablet

- Collapsible sidebar
- POS optimized for touch
- Two-panel receipt review if space allows

### 33.6 Admin Mobile

- Bottom nav
- Single-column layouts
- Full-screen drawers
- Quick actions emphasized
- Complex reporting can be simplified

## 34. Copywriting Rules

Use clear, direct copy.

Tone:

- Friendly
- Helpful
- Confident
- Plain English
- Not corporate
- Not childish
- Not too wordy

Button rules:

- Start with a verb.
- Say exactly what happens.
- Avoid vague text like `Submit` when `Send Request` is clearer.

Good public buttons:

- Shop Products
- Request a Custom Print
- See Upcoming Markets
- Contact Us
- Upload Your Idea
- Add to Cart
- Start Custom Order

Good admin buttons:

- Add Product
- Start Sale
- Complete Sale
- Upload Receipt
- Review Receipt
- Create Market
- Publish Event
- Send Quote
- Adjust Inventory

Error message rules:

- Explain what happened.
- Tell the user what to do next.
- Avoid blaming the user.

## 35. Dynamic Features

Use modern features only when they make the business better.

Good features:

- Cart drawer
- Custom order wizard
- Secure file uploads
- Quote request tracker
- Event map
- Product filters
- Live search
- Customer gallery
- Request something similar
- Back-in-stock notifications
- Order status lookup
- Recently viewed products
- Admin-manageable homepage sections
- AI-assisted receipt review
- AI-assisted analytics summaries
- Market prep checklist
- POS market mode
- Audit trail views

Avoid:

- Random animations
- 3D effects that slow phones
- Chatbots that guess business policies
- Fake urgency banners
- Fake reviews
- Confetti on serious admin actions

## 36. Integration Design

Expected integrations:

- Payment provider for secure checkout
- DFPos order management
- Inventory sync
- Custom order intake
- Email notifications
- Contact form delivery
- Market/event calendar
- Analytics
- Spam protection
- File storage
- Shipping/pickup handling
- Audit logging microservice
- Optional OpenAI/ChatGPT for receipt review and analytics summaries

### 36.1 Public to DFPos Data Flow

Public site sends to DFPos:

- Orders
- Cart line items
- Customer contact info
- Custom order requests
- Uploaded files metadata
- Market inquiry messages
- Product interest/back-in-stock requests

DFPos sends to public site:

- Public products
- Public categories
- Product availability
- Featured products
- Public market events
- Gallery items
- FAQ entries
- Policy pages
- Contact settings

Payment data rule:

- Raw payment data must never flow through DFPos unless handled through a compliant provider tokenized flow.

## 37. Tailwind and CSS Implementation Rules

Use Tailwind if it is already part of the project, but do not let Tailwind turn the codebase into color spaghetti.

Rules:

- Map design tokens to Tailwind theme values.
- Use semantic utility classes where possible.
- Prefer reusable components over duplicated class blobs.
- No hardcoded hex colors in templates.
- No one-off radius values unless added to tokens.
- Keep responsive classes consistent.
- Create shared layout components for public and admin shells.

Recommended CSS variables can live in:

```text
app/static/css/tokens.css
app/static/css/base.css
app/static/css/components.css
```

or the equivalent project structure.

## 38. Developer Implementation Rules

A coding agent must follow these rules.

1. Build reusable components.
2. Use design tokens only.
3. Avoid hardcoded colors.
4. Keep layouts responsive.
5. Optimize images.
6. Support accessibility from the start.
7. Validate all forms client-side and server-side.
8. Secure file uploads.
9. Never store raw payment data.
10. Protect customer information.
11. Keep checkout simple.
12. Keep POS faster than fancy.
13. Avoid unnecessary animations.
14. Include loading, empty, error, validation, and success states.
15. Make public content easy to update from admin.
16. Avoid generic template design.
17. Preserve DudeFish Printing brand personality.
18. Do not invent business policies.
19. Do not create fake testimonials.
20. Do not add unsupported claims.
21. Do not expose admin-only data on the public site.
22. Log every important action to the audit service.
23. Do not silently fail. Show the user what happened.
24. Keep public pages friendly and admin pages efficient.
25. Treat mobile and tablet layouts as real, not afterthoughts.

## 39. Module Design Checklist

Every module must answer these questions before implementation is considered done.

- What is the main action on this page?
- What does the user need to know first?
- What can go wrong?
- What does loading look like?
- What does empty look like?
- What does success look like?
- What does failure look like?
- What should be logged?
- What data is public and what data is private?
- What happens on mobile?
- What happens with keyboard navigation?
- What happens if the network fails?

## 40. Public Page Definition of Done

A public page is done when:

- It follows the design tokens.
- It matches the DudeFish visual direction.
- It is responsive.
- It has real content or clearly marked placeholders.
- It has loading, empty, and error states where needed.
- It is keyboard accessible.
- It has meaningful meta title and description.
- Images are optimized and have alt text.
- Forms validate correctly.
- Security requirements are met.
- It does not expose private admin data.

## 41. Admin Page Definition of Done

An admin page is done when:

- It uses the admin shell.
- It has a clear title, description, and primary action.
- It supports search/filter/sort where useful.
- It has loading, empty, error, and success states.
- It is responsive for desktop and tablet.
- It is usable by keyboard.
- It logs important changes.
- It prevents destructive mistakes.
- It handles permission denied states.
- It does not rely on fake data.
- It links related records cleanly.

## 42. POS Definition of Done

The POS is done when:

- Products can be searched and added quickly.
- Cart quantity edits are obvious.
- Totals are clear.
- Payment method is recorded clearly.
- Cash/external payments are not confused with processed card payments.
- Refunds and voids require confirmation.
- Inventory updates are accurate.
- Every sale/refund/void is audit logged.
- Market mode works on tablet.
- The screen stays fast with real product counts.
- Offline/unavailable states are considered.

## 43. Receipt Review Definition of Done

Receipt review is done when:

- Upload works for supported files.
- Extraction status is visible.
- Low-confidence fields are marked.
- The user can edit metadata.
- The user can assign line items.
- Tax/fee allocation is visible.
- Inventory creation/update prompts work.
- Posting a receipt is explicit.
- All edits are audit logged.
- The original receipt remains available.

## 44. Final Visual North Star

The public website should look like the Figma screenshots: warm, clean, rounded, modern, orange and teal accents, strong navy moments, dark footer, clear cards, and friendly forms.

The admin side should feel like the same product grew up into a serious business tool. Keep the warmth, but tighten the spacing. Keep the rounded cards, but make the data scannable. Keep the orange and teal, but use them with discipline. Keep the family-run personality, but do not let it get in the way of speed.

DFPos should feel like DudeFish Printing built its own operating system because generic tools were too clunky.

That is the bar.
