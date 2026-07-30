## Implementation Plan

### Phase 0 — Foundation
- Add **Cabinet Grotesk** (self-hosted woff2 in `app/static/src/fonts/`)
- Update Tailwind config with new font family, new spacing/motion tokens
- Create `app/static/src/js/gsap-animations.js` — centralized GSAP utilities (observe, scrub, stagger)
- Create `app/static/src/css/gsap-layouts.css` — glass, bento, masonry component classes
- **Design tokens**: Add glass/backdrop blur tokens, update shadows for cinematic depth

### Phase 1 — Public Website Redesign
| Template | gpt-taste treatment |
|---|---|
| `_header.html` | **Glassmorphism floating pill nav** — sticky, `backdrop-blur-xl`, transparent bg, white text on hero, dark on scroll |
| `home.html` | **Artistic Asymmetry Hero** — 60% text left (oversized H1), filament graphic floats from bottom-right with parallax. Bento grid for product lanes. Split-screen "About" with counter GSAP. Timeline strip for custom orders. Scrubbing text reveals throughout. |
| `shop.html` | **Masonry product grid** with Image Scale & Fade scroll. Glass filter bar. |
| `product_detail.html` | **Split-screen** gallery left, buy panel right with sticky scroll. |
| `cart.html` | **Glass drawer redesign**, floating totals with backdrop blur. |
| `checkout.html` | **Timeline step indicator** with GSAP progress scrubbing. |
| `custom_orders.html` | **Horizontal timeline strip** with scroll-triggered step reveals. |
| `gallery.html` | **Full masonry** with Image Scale & Fade + lightbox GSAP transitions. |
| `about.html` | **Split screen** with counter animation stats. |
| `_footer.html` | **Ink-navy with floating glass CTA** — "Start your custom order" pill floats above footer. |

### Phase 2 — Admin Dashboard Redesign
| Area | gpt-taste treatment |
|---|---|
| `_sidebar.html` | **Glass sidebar** — `backdrop-blur-md`, subtle border, hover physics on nav items |
| `dashboard/` | **Bento grid dashboard** — 3-5 purpose-built cards with GSAP staggered entrance. Key metrics with counter animation. |
| CRUD tables | **Data with motion** — rows fade in with staggered reveals, sticky glass header |
| Cards/forms | **Floating glass cards** for forms, bento for detail views |

### Phase 3 — POS Redesign
| Area | gpt-taste treatment |
|---|---|
| Layout | **Split with glass divider** — product grid left, glass cart panel right |
| Product tiles | **Cinematic tiles** with hover scale physics, glass category pills |
| Cart | **Glass drawer/pin** with floating total and GSAP line-item adds |
| Checkout flow | **Timeline step** with GSAP progress |

### Phase 4 — Cross-cutting
- All loading states get **GSAP skeleton pulse** animations
- Empty states get **cinematic illustration + reveal animation**
- Error states get **shake/attention GSAP**
- `prefers-reduced-motion` globally disables GSAP via `gsap.matchMedia()`
- Responsive: glass nav collapses, masonry becomes single column, animations downgrade

---

**Before we start**: This touches ~50+ templates, ~3 CSS files, ~5 new JS files, font hosting, and significant Tailwind config changes. Would you like to proceed Phase 0 first (foundation + one or two key templates to validate the direction), or tackle the public homepage as a proof of concept?