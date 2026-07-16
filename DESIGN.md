# Dude Fish Printing / DFPos Design System

This file is the single design source of truth for the Dude Fish Printing public storefront and
the DFPos internal application. It replaces all previous Figma-era guidance and older versions
of `DESIGN.md`.

The public site and internal app are one product family with different working densities:

- Public storefront: warm, clear, playful, trustworthy, and easy to shop on a phone.
- Admin: calm, compact, data-rich, and optimized for repeat work.
- POS: touch-first, fast, forgiving, and usable during a crowded market.

When this document conflicts with an existing template, the template should be migrated toward
this document. Business behavior and security requirements in `AGENTS.md` still take precedence.

## 1. Product identity

### The Friendly Print Studio

Dude Fish Printing is a working family print studio, not a generic craft marketplace, toy store,
or SaaS company. Its visual language comes from filament spools, visible print layers, articulated
forms, material swatches, and the satisfying moment when an idea becomes a physical object.

The public site's primary job is to help a visitor choose one of two paths:

1. Shop prints that are ready or made to order.
2. Describe a custom idea without needing 3D-printing knowledge.

DFPos's primary job is to tell the owner or helper what needs attention and make the next action
safe and obvious.

### Brand character

- Friendly, never childish
- Colorful, never chaotic
- Knowledgeable, never technical for its own sake
- Local and human, never artificially folksy
- Practical enough for a business, warm enough for a gift

Do not imitate a generic admin template. Do not use decorative analytics, floating glass cards,
rainbow gradients, fake social proof, or invented business claims.

## 2. Design foundations

All visual values must be exposed as CSS custom properties. Templates and scripts must not contain
raw color values.

### Color

| Token | Default | Purpose |
|---|---:|---|
| `--color-canvas` | `#fff8ed` | Warm public canvas |
| `--color-surface` | `#ffffff` | Cards and elevated surfaces |
| `--color-ink` | `#10233f` | Headings, hero, footer, trust |
| `--color-text` | `#182438` | Primary body text |
| `--color-muted` | `#657083` | Supporting text |
| `--color-line` | `#ded8cc` | Borders and dividers |
| `--color-primary` | `#ff6243` | Purchase and primary actions |
| `--color-primary-hover` | `#e64d32` | Primary hover/pressed family |
| `--color-secondary` | `#12afa3` | Custom work, help, and focus |
| `--color-secondary-hover` | `#087f78` | Secondary hover/pressed family |
| `--color-highlight` | `#f5c451` | Small highlights only |
| `--color-success` | `#26845b` | Confirmed and healthy states |
| `--color-warning` | `#b66a10` | Needs attention |
| `--color-danger` | `#c73b3b` | Destructive and failed states |
| `--color-info` | `#256f9c` | Neutral system information |

Rules:

- Coral is the principal commercial action: shop, add to cart, checkout, save.
- Teal is the custom/support path and the focus-ring color.
- Yellow is emphasis, not a third CTA color.
- Semantic colors communicate status only and always appear with text or an icon.
- Public dark sections use ink navy. Avoid pure black.
- Internal dark mode may remap surfaces, text, borders, and semantic colors while keeping their
  meanings and WCAG contrast.

### Typography

Use locally available or self-hosted fonts. The interface must not depend on a third-party font
request.

```css
--font-display: "Arial Rounded MT Bold", "Avenir Next", ui-rounded, system-ui, sans-serif;
--font-body: "Avenir Next", "Nunito Sans", ui-sans-serif, system-ui, sans-serif;
--font-data: "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
```

- Display type is reserved for public hero and section headlines.
- Body/UI type is used everywhere else.
- Data type is limited to SKUs, order numbers, API tokens, technical identifiers, and dense
  tabular figures.
- Use sentence case. Uppercase is limited to short contextual labels at `12px` or larger.
- Public body text is at least `16px`; admin supporting text is at least `13px`.
- Use tabular numbers for prices, counts, costs, and analytics.

Type scale:

| Role | Size | Line height |
|---|---:|---:|
| Hero | `clamp(56px, 8vw, 108px)` | `0.90` |
| Public H1 | `clamp(42px, 6vw, 72px)` | `0.98` |
| Public H2 | `clamp(34px, 4vw, 58px)` | `1.02` |
| Admin H1 | `28px` | `1.2` |
| H3/card title | `18–22px` | `1.3` |
| Public body | `16–20px` | `1.6` |
| Admin body | `14–16px` | `1.45` |
| Utility/meta | `12–13px` | `1.4` |

### Spacing and layout

Use a four-pixel base scale:

```css
--space-1: 4px;  --space-2: 8px;  --space-3: 12px; --space-4: 16px;
--space-5: 20px; --space-6: 24px; --space-8: 32px; --space-10: 40px;
--space-12: 48px; --space-16: 64px; --space-20: 80px; --space-24: 96px;
```

- Public content: maximum `1180px`; reading/forms: maximum `760px`.
- Public section padding: `72–112px` desktop, `56–72px` mobile.
- Admin: fluid width with `24px` desktop and `16px` mobile padding.
- POS: full viewport; do not wrap it in the public or admin content container.
- Prefer alignment and whitespace over nested cards.

### Shape and depth

```css
--radius-sm: 10px;
--radius-md: 14px;
--radius-lg: 20px;
--radius-xl: 28px;
--radius-pill: 999px;
--shadow-card: 0 8px 30px rgb(16 35 63 / 0.08);
--shadow-overlay: 0 24px 70px rgb(16 35 63 / 0.20);
```

- Buttons are pills or `14px` rounded rectangles.
- Public feature cards use `20–28px`; admin cards use `14–20px`.
- Default cards use borders without shadows. Apply shadow only for hover, drawers, popovers,
  and modals.
- Dense tables may have square internal cells inside a rounded outer container.

### Icons and imagery

- Use one consistent outline icon family at approximately `1.75–2px` stroke.
- Label unfamiliar icons. Every icon-only control needs an accessible name and tooltip when useful.
- Product cards use real product photography. If none exists, show a deliberate studio placeholder
  reading `Photo coming soon`; never synthesize a product representation in normal UI.
- Use consistent crop ratios within one shelf or grid.
- Decorative imagery must have empty alt text. Product imagery needs useful alt text.

## 3. Shared interaction system

### Buttons

Every page has one visually dominant action.

- Primary: solid coral; purchase, checkout, save, publish, or complete.
- Secondary: solid teal or teal outline; custom/support/helpful next path.
- Neutral: ink outline or quiet surface; cancel, back, filters, secondary navigation.
- Destructive: red text or solid red only within a confirmation context.
- Disabled: visibly muted and programmatically disabled; provide the reason nearby when unclear.

Button labels use plain verbs: `Save changes`, `Add to cart`, `Approve receipt`, `Close session`.
Do not use `Submit`, `Continue` without context, or icon-only primary actions.

Minimum target size is `44×44px`; POS targets are at least `52×52px`.

### Forms

- Labels always remain visible above fields.
- Helper text explains constraints before validation.
- Errors appear beside the field and in an accessible summary for long forms.
- Required fields are identified in text, not color alone.
- Inputs use a visible teal focus ring and outer surface keyline.
- Preserve user input after validation errors.
- Cancel/back actions are available for multi-step and admin forms.
- File inputs show allowed types, maximum size, progress, preview/name, and removal.

### Cards

Use cards only to group one coherent object or action. A card needs no shadow by default. Avoid a
page made entirely of equally weighted cards. Make product cards, status summaries, and next-action
panels structurally distinct.

### Badges

Badges are short nouns or states: `Active`, `Needs review`, `Low stock`, `Paid`. Use soft semantic
backgrounds, readable text, and a non-color signal when the distinction is important.

### Tables and lists

Admin tables provide, when relevant:

- Search and meaningful filters
- Sortable columns with current direction announced
- Sticky headers for long tables
- Status text, tabular figures, and predictable row actions
- Pagination or incremental loading
- Bulk actions only when safe
- Mobile transformation into a prioritized list, not a squeezed desktop table

Selection must never be the same click target as row navigation.

### Overlays and feedback

- Use drawers for contextual editing and POS cart behavior.
- Use modals for short decisions, confirmations, or destructive warnings—not long forms.
- Toasts confirm background or low-risk actions and must not contain essential information only.
- Inline banners explain persistent page-level problems.
- Focus moves into opened overlays and returns to the trigger when closed.

## 4. Public storefront

### Public navigation

The public navbar is part of the brand, not an admin-style utility bar.

Desktop:

- Sticky cream header, approximately `72–76px` tall
- Dude Fish brand mark at left
- Links: `Shop`, `Markets`, `Gallery`, `Learn`, `Our story`
- Teal `Start a custom order` CTA
- Cart control with real item count

Mobile:

- Brand left; cart and `Menu` right
- Menu opens below the header with large vertical targets
- `Shop` and `Start a custom order` remain the strongest choices
- Menu closes after navigation and supports Escape when implemented as a disclosure/drawer

Do not include staff sign-in in the primary public navigation. It may live in the footer.
Show the current page state using `aria-current="page"` and a visible soft background or underline.

### Homepage

Information order:

1. Hero: what is made, where it is made, and the two shopping paths.
2. Real product lanes: playful, personalized, local, and useful.
3. Featured products from live catalog data or an honest empty state.
4. Ordered custom workflow: share idea, choose details, approve quote, receive print.
5. Next market from live data; omit or show a truthful empty state when none exists.
6. Plain-English printing/material help.
7. Final contact/custom-order invitation.

The hero uses an ink-navy stage with an oversized layered filament path forming a friendly abstract
fish/print object. This is the public site's single expressive visual signature. Keep surrounding
sections quiet. Replace the center with an approved real product photo when suitable photography
exists while retaining the filament path.

Hero copy must identify 3D printing and Clarksville without jargon. Primary action: shop. Secondary
action: custom order. Never add invented review counts, turnaround times, customer totals, or trust
statistics.

### Shop and collection pages

- Search comes first on mobile.
- Categories are readable pills or a compact select; selected filters are obvious and removable.
- Show result count and active filters.
- Grid: four columns at wide desktop, three laptop, two tablet, one or two mobile depending on
  image readability.
- Keep sorting limited to useful real options.
- End with a custom-order path for shoppers who did not find the right item.

Product cards contain image, real badge if applicable, category, name, price, availability, and
an obvious details/add action. Ratings appear only when a real review system exists. Entire image
and title link to details; purchase action remains separate.

### Product detail

Desktop uses gallery left and purchase information right. Mobile places title, price, availability,
and first image before options. Show:

- Name, category, price, availability
- Real photos and variants
- Size, material, care, and relevant safety information
- Color/personalization choices with labels
- Quantity and add-to-cart action
- Pickup/shipping information derived from configuration
- Custom-request escape hatch when standard options are insufficient

Do not bury dimensions, material, processing expectations, or care notes.

### Cart and checkout

- Cart shows editable quantity, line price, subtotal, fulfillment choice, and removal.
- Checkout uses a narrow, linear layout with an always-readable order summary.
- Never show card number or CVV inputs. External payment handoff is named clearly.
- Errors preserve cart and form state and explain exactly how to continue.
- Confirmation shows the real order number and next step without unsupported promises.

### Custom orders

Use an ordered four-step flow because sequence matters:

1. Idea: plain-language description and optional safe file upload.
2. Details: approximate size, quantity, color, material, deadline, and budget where available.
3. Contact: name, email, optional phone, fulfillment preference, and notes.
4. Confirmation: what was received and what happens next.

The interface states clearly that rough ideas are welcome and no payment occurs before quote
approval. Completed steps use teal with a check; active step uses coral; upcoming steps are neutral.

### Markets, gallery, learn, and content pages

- Markets use live event data with date, location, status, accessibility/parking notes when known,
  and directions only from configured locations.
- Gallery uses real work with title/category and a `Request something like this` action.
- Learn explains PLA/PETG, layer lines, care, durability, color variation, and realistic limits in
  ordinary language.
- FAQ uses semantic disclosure controls and supports direct linking to questions.
- Policies remain clearly labeled placeholders until approved business language is supplied.
- Contact routes custom work to the custom form and general questions to a concise contact form.

### Public footer

Use an ink-navy footer with brand summary, shop links, information links, legal links, and configured
contact/location information. Never hardcode unverified email, hours, address, social account, or
policy claims. Staff sign-in may appear as a quiet utility link.

## 5. Admin and DFPos

### Application shell

- Desktop: persistent ink or neutral sidebar, compact context bar, fluid content.
- Tablet: collapsible sidebar; preserve page title and primary action.
- Mobile: drawer navigation and prioritized content; never depend on horizontal page scrolling.
- Navigation comes from the module registry and respects permissions and feature flags.
- Disabled modules are hidden from staff and shown as clearly locked to admins only when useful.

Page header order:

1. Breadcrumb or module context
2. Page title and concise state/description
3. Primary action
4. Secondary actions or overflow

### Dashboard

The dashboard answers `What needs attention now?`, not merely `What are the totals?`

Prioritize:

- Urgent custom orders and overdue prep
- Receipts needing review
- Low inventory and production blockers
- Upcoming market readiness
- Failed or stalled print jobs
- Cash/session discrepancies

Summary metrics include comparison context or a reason to act. Avoid decorative charts and do not
present demo analytics as real.

### CRUD screens

- Lists optimize scanning and filtering.
- Detail pages show current status, important relationships, history, and next actions.
- Create/edit forms group fields by the user's decision, not database table structure.
- Archive is preferred for important business records.
- Destructive actions state impact and require confirmation.
- Audit history is available near sensitive records when practical.

### Inventory and products

- Inventory always identifies product/variant, location, available/reserved quantity, and status.
- Adjustment flows require direction, quantity, reason, and location context.
- Product screens surface SKU, price, cost/margin, public/POS visibility, license status, stock, and
  production details without mixing them into one unstructured form.
- License/compliance warnings are prominent and never represented as marketing badges.

### Receipts & Expenses

Receipt review is a comparison workflow:

- Source image/document remains visible beside extracted fields on desktop.
- Mobile alternates clearly between source and fields without losing edits.
- AI values are labeled suggestions with confidence when available.
- Differences and validation problems are obvious.
- Approval explains which ledger entries will be created or updated.
- `Approve receipt` is unavailable until required review conditions are satisfied.
- Duplicate warnings identify the matching vendor/date/amount evidence.

### Markets and prep

Market detail combines event facts, application status, financials, packing, tasks, sales, and
readiness without one endless form. The primary view answers:

- Are we going?
- Are we ready?
- What should we bring or print?
- What remains incomplete?
- Was this market profitable?

Readiness scores always show their inputs; a score alone is not actionable.

### Analytics

Each analytics view starts with the business question, then shows the supporting number/table/chart,
then the recommended action when justified.

- Chart.js is the default chart library.
- Charts use the token palette and never color categories randomly between views.
- Axes include units; money and percentages are formatted correctly.
- Every chart has a text/table alternative or accessible summary.
- AI explanations may interpret only real displayed data and are labeled as generated insight.
- Empty and insufficient-data states explain what data is needed.

### Audit logs and settings

- Audit entries prioritize time, actor, action, entity, outcome, and request ID.
- Before/after data is readable as a structured diff, not an undifferentiated JSON wall.
- Sensitive tokens and secrets are always redacted.
- Settings show scope, current source (default/database), effect, and whether restart is needed.
- Feature flag changes clearly describe affected routes/navigation and are treated as sensitive.

## 6. POS

POS is a dedicated full-viewport work surface. Decoration is secondary to speed and error prevention.

### Layout

- Desktop/tablet: product discovery left, cart right, session/market context fixed at top.
- Phone: product grid with cart drawer and persistent cart total/action.
- Category controls scroll horizontally without tiny targets.
- Product search is immediately reachable and tolerant of SKU/name input.
- Product tiles show short name, price, availability, and color/photo cue when useful.

### Cart and checkout

- Quantity controls and remove actions are large and separated.
- Total is always visible once the cart has items.
- Payment method choices are explicit: cash and configured external/placeholders only.
- Cash flow shows amount tendered, change due, and a final confirmation.
- No card number, expiration, or CVV fields exist anywhere.
- Completion cannot be triggered twice; show a clear in-progress state.

### Error prevention and recovery

- Session, market, inventory location, and cashier context are visible.
- Low/out-of-stock warnings occur before final sale.
- Void/refund actions are separated from routine checkout and state their consequences.
- Network or audit failures explain whether the sale was recorded and what staff should do next.
- Closed sessions visibly lock new sales.
- Destructive or financial actions use explicit confirmation and audit outcomes.

## 7. System states and writing

Every dynamic screen implements relevant states:

- Loading: skeleton for content, spinner only for a small local action, descriptive text for long work.
- Empty: what is missing, why it matters, and the next action.
- Error: what failed, whether work was saved, and how to recover.
- Validation: field-specific guidance without clearing input.
- Success: name the completed action using the same verb as the control.
- Partial/stale: label delayed or incomplete data and the last successful update.
- Permission denied: explain access limits without exposing sensitive details.
- Module disabled: enforce server-side and explain availability appropriately for the role.

Copy uses active voice, plain verbs, and terms customers/staff recognize. A label labels, helper text
helps, and a button states the action. Avoid clever headings when clarity would be faster.

## 8. Accessibility

WCAG 2.2 AA is the minimum target.

- All functions work with keyboard only.
- Focus is always visible and follows logical reading order.
- Skip link targets the main content.
- Landmarks, headings, labels, and table headers are semantic.
- Color is never the only signal.
- Text contrast is at least `4.5:1`; large text/UI graphics at least `3:1` where applicable.
- Touch targets are at least `44×44px`; POS uses `52px` where practical.
- Modals/drawers manage focus and Escape correctly.
- Live updates and validation summaries use appropriate announcements without excessive interruption.
- Images have meaningful alt text or empty alt text when decorative.
- Charts include accessible summaries or tables.
- `prefers-reduced-motion` removes nonessential animation.
- Content remains usable at 200% zoom and at a `320px` viewport.

## 9. Responsive behavior

Design mobile states intentionally; desktop wrapping is not a mobile design.

Breakpoints are content-driven, with these expected ranges:

- Compact/mobile: below `640px`
- Tablet: `640–1023px`
- Desktop: `1024px` and above
- Wide: `1280px` and above

Public hero, custom-order split, market band, and footer columns stack on compact screens. Product
controls prioritize search, active filters, and results before optional sort. Admin tables convert
to prioritized cards/lists when essential columns cannot fit. POS never forces the checkout action
below a long product list.

## 10. Motion and performance

Spend boldness in one place: the homepage filament hero may settle on initial load. Elsewhere use
only short transitions for state, hover, drawers, and feedback.

- Standard transition: `120–200ms`.
- Avoid scroll-jacking, perpetual ambient motion, parallax, and loading animation after content is ready.
- Respect reduced motion.
- Server-render meaningful HTML first.
- Reserve image dimensions to prevent layout shift.
- Lazy-load below-the-fold images and keep product images appropriately sized.
- HTMX is preferred for small server interactions; Alpine.js is limited to local disclosure/state.
- POS may use its approved small Preact island, but public/admin pages remain server rendered.

## 11. Tailwind and CSS implementation

- Tailwind handles layout and utility composition.
- Semantic component classes and CSS variables carry the brand system.
- Do not use arbitrary color utilities in templates.
- Do not use inline `style` attributes for colors, spacing, or normal component appearance.
- Keep public, admin, and POS variants explicit; do not pile context overrides onto one selector.
- Reusable Jinja components should cover buttons, fields, badges, alerts, empty states, pagination,
  product cards, admin tables, and modal/drawer frames where practical.
- Build CSS through the repository's npm script and commit generated assets only if repository policy
  tracks them.

## 12. Security-sensitive design

- Never display or log password hashes, token hashes, secrets, full credentials, or card data.
- Mask API tokens after creation and make one-time visibility explicit.
- Upload UI lists allowed types and sizes; server validation remains authoritative.
- Permission and feature-flag enforcement is server-side. Hidden UI is not security.
- Financial actions show final amounts and consequences before confirmation.
- Audit failure states for critical actions must match configured fail-open/fail-closed behavior.
- External payment handoffs identify the provider and return state without implying DFPos stores cards.

## 13. Definition of done

A screen is visually complete only when:

- It uses semantic tokens and the correct public/admin/POS density.
- Its main action is obvious and labels are plain language.
- Real, empty, loading, error, validation, and success states are handled where relevant.
- It works at `320px`, tablet, desktop, 200% zoom, keyboard-only, and reduced motion.
- Forms retain input after errors and destructive actions confirm impact.
- Feature flags and permissions affect both navigation and server behavior.
- Dynamic values come from real application data or are explicitly labeled demo/placeholder.
- It does not introduce fake claims, reviews, locations, policies, analytics, or product imagery.
- Relevant audit and security behavior is visible and tested.
- CSS builds without errors and focused route/template tests pass.

## 14. Visual review checklist

Before accepting a new UI, ask:

1. Could this page belong to an unrelated SaaS product or craft shop? If yes, ground it more deeply
   in Dude Fish's products or workflow.
2. Is there one clear action, or are several controls shouting equally?
3. Are cards being used for meaning, or merely because empty space felt uncomfortable?
4. Does the mobile layout preserve the actual task rather than just stack the desktop layout?
5. Can a tired market helper recover from the most likely mistake?
6. Does every number, claim, location, status, and image come from real data or an honest placeholder?
7. Can the page be understood and operated without color, a mouse, animation, or specialist language?

The visual north star is a warm local print studio on the public side and a reliable operating
cockpit on the inside: clearly the same Dude Fish family, designed for two different jobs.
