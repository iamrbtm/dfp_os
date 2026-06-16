# OpenCode Prompt: Phase 4.5 Theme System and Theme Library

You are working on Dude Fish OS.

This is Phase 4.5. Do not rebuild the whole application. Add a production-ready theme system that affects the entire program: public website, admin dashboard, CRUD pages, analytics pages, POS, forms, tables, modals, alerts, nav/sidebar, cards, buttons, badges, charts, and any reusable components.

Read these files first:

- AGENTS.md
- DESIGN.md
- README.md
- app/config.py
- app/__init__.py
- app/templates/**
- app/static/**
- tailwind.config.* if present
- pyproject.toml
- package.json if present

Before coding, inspect the current styling architecture and summarize:

1. Where global styling currently lives.
2. How Tailwind is configured.
3. How base templates are organized.
4. Which templates/components need theme tokens.
5. Whether POS has a separate frontend island and how it should consume the same theme system.
6. Any risks or files that should not be touched.

Then implement the theme system.

## Goal

Create a complete user-selectable theme system with 10 built-in themes:

Five light themes:

1. DFP GitHub Light
2. DFP Atom One Light
3. DFP Catppuccin Latte
4. DFP Ayu Light
5. DFP Quiet Light

Five dark themes:

1. DFP One Dark Pro
2. DFP Dracula
3. DFP GitHub Dark
4. DFP Tokyo Night
5. DFP Catppuccin Mocha

These should be app-theme adaptations inspired by popular editor/UI theme families. Do not claim these are official themes. Do not use third-party logos or trademarks in the UI beyond descriptive theme names. Put a small note in the settings page that themes are "inspired by familiar developer color palettes and adapted for Dude Fish OS." Use names internally as slugs.

The theme must ripple throughout the entire program. No half-theme nonsense. Backgrounds, cards, borders, text, muted text, buttons, button borders, inputs, selects, tables, tabs, badges, nav, sidebar, modals, alerts, POS tiles, cart panel, checkout buttons, analytics charts, focus rings, hover states, empty states, and print views must all use theme tokens.

## Required Implementation Approach

Use CSS custom properties as the source of truth.

Create a centralized theme registry and token system.

Preferred files:

```text
app/theme_registry.py
app/blueprints/settings/theme_routes.py
app/templates/settings/themes.html
app/static/src/css/theme-tokens.css
app/static/src/css/app.css
app/static/src/js/theme-switcher.js
```

Adjust paths to match the existing project structure.

Each theme must expose a consistent set of CSS variables under `[data-theme="theme-slug"]`.

Example:

```css
:root,
[data-theme="dfp-github-light"] {
  --color-bg: #ffffff;
  --color-bg-subtle: #f6f8fa;
  --color-surface: #ffffff;
  --color-surface-raised: #f6f8fa;
  --color-border: #d0d7de;
  --color-border-strong: #afb8c1;
  --color-text: #24292f;
  --color-text-muted: #57606a;
  --color-text-soft: #6e7781;
  --color-primary: #0969da;
  --color-primary-hover: #0757b8;
  --color-primary-text: #ffffff;
  --color-secondary: #6e7781;
  --color-secondary-hover: #57606a;
  --color-secondary-text: #ffffff;
  --color-accent: #8250df;
  --color-accent-hover: #6639ba;
  --color-success: #1a7f37;
  --color-warning: #9a6700;
  --color-danger: #cf222e;
  --color-info: #0969da;
  --color-input-bg: #ffffff;
  --color-input-border: #d0d7de;
  --color-input-focus: #0969da;
  --color-button-border: #0969da;
  --color-button-ghost-hover: #f6f8fa;
  --color-table-header: #f6f8fa;
  --color-table-row-hover: #f6f8fa;
  --color-sidebar-bg: #f6f8fa;
  --color-sidebar-text: #24292f;
  --color-sidebar-active-bg: #eaeef2;
  --color-sidebar-active-text: #0969da;
  --color-pos-tile-bg: #ffffff;
  --color-pos-tile-border: #d0d7de;
  --color-pos-tile-hover: #f6f8fa;
  --color-cart-bg: #ffffff;
  --color-focus-ring: rgba(9, 105, 218, 0.35);
  --shadow-card: 0 1px 2px rgba(31, 35, 40, 0.08);
  --shadow-popover: 0 8px 24px rgba(31, 35, 40, 0.12);
}
```

Add additional variables if needed.

## Required Token Categories

Each theme must define at least:

### Base

- `--color-bg`
- `--color-bg-subtle`
- `--color-bg-inset`
- `--color-surface`
- `--color-surface-raised`
- `--color-surface-muted`
- `--color-border`
- `--color-border-strong`
- `--color-divider`

### Text

- `--color-text`
- `--color-text-muted`
- `--color-text-soft`
- `--color-text-inverted`
- `--color-link`
- `--color-link-hover`

### Brand and Actions

- `--color-primary`
- `--color-primary-hover`
- `--color-primary-active`
- `--color-primary-text`
- `--color-secondary`
- `--color-secondary-hover`
- `--color-secondary-text`
- `--color-accent`
- `--color-accent-hover`
- `--color-accent-text`

### Status

- `--color-success`
- `--color-success-bg`
- `--color-warning`
- `--color-warning-bg`
- `--color-danger`
- `--color-danger-bg`
- `--color-info`
- `--color-info-bg`

### Form Controls

- `--color-input-bg`
- `--color-input-border`
- `--color-input-text`
- `--color-input-placeholder`
- `--color-input-focus`
- `--color-checkbox-bg`
- `--color-checkbox-border`

### Buttons

- `--color-button-border`
- `--color-button-ghost-hover`
- `--color-button-disabled-bg`
- `--color-button-disabled-text`

### Tables and Lists

- `--color-table-header`
- `--color-table-row-hover`
- `--color-table-selected`
- `--color-table-border`

### Navigation

- `--color-nav-bg`
- `--color-nav-border`
- `--color-nav-text`
- `--color-nav-muted`
- `--color-nav-active-bg`
- `--color-nav-active-text`
- `--color-sidebar-bg`
- `--color-sidebar-border`
- `--color-sidebar-text`
- `--color-sidebar-muted`
- `--color-sidebar-active-bg`
- `--color-sidebar-active-text`

### POS

- `--color-pos-bg`
- `--color-pos-toolbar-bg`
- `--color-pos-tile-bg`
- `--color-pos-tile-border`
- `--color-pos-tile-hover`
- `--color-pos-tile-text`
- `--color-pos-category-bg`
- `--color-pos-category-active-bg`
- `--color-pos-cart-bg`
- `--color-pos-cart-border`
- `--color-pos-checkout-bg`
- `--color-pos-checkout-hover`
- `--color-pos-checkout-text`
- `--color-pos-cash-bg`
- `--color-pos-card-placeholder-bg`

### Charts

- `--chart-1`
- `--chart-2`
- `--chart-3`
- `--chart-4`
- `--chart-5`
- `--chart-grid`
- `--chart-axis`
- `--chart-tooltip-bg`
- `--chart-tooltip-text`

### Effects

- `--color-focus-ring`
- `--shadow-card`
- `--shadow-popover`
- `--radius-sm`
- `--radius-md`
- `--radius-lg`

## Theme Palette Guidance

Use these palettes as starting points. Adjust only enough to meet readable contrast and app usability.

### 1. DFP GitHub Light

Slug: `dfp-github-light`

Personality: clean, neutral, familiar, businesslike.

Approximate colors:

- bg: `#ffffff`
- bg subtle: `#f6f8fa`
- surface: `#ffffff`
- surface raised: `#f6f8fa`
- border: `#d0d7de`
- border strong: `#afb8c1`
- text: `#24292f`
- muted text: `#57606a`
- primary: `#0969da`
- accent: `#8250df`
- success: `#1a7f37`
- warning: `#9a6700`
- danger: `#cf222e`

### 2. DFP Atom One Light

Slug: `dfp-atom-one-light`

Personality: soft white, readable, code-editor clean.

Approximate colors:

- bg: `#fafafa`
- bg subtle: `#f0f0f0`
- surface: `#ffffff`
- surface raised: `#f5f5f5`
- border: `#d9d9d9`
- border strong: `#c4c4c4`
- text: `#383a42`
- muted text: `#696c77`
- primary: `#4078f2`
- accent: `#a626a4`
- success: `#50a14f`
- warning: `#c18401`
- danger: `#e45649`

### 3. DFP Catppuccin Latte

Slug: `dfp-catppuccin-latte`

Personality: warm pastel, friendly, soft, modern.

Approximate colors:

- bg: `#eff1f5`
- bg subtle: `#e6e9ef`
- surface: `#ffffff`
- surface raised: `#f7f8fb`
- border: `#ccd0da`
- border strong: `#bcc0cc`
- text: `#4c4f69`
- muted text: `#6c6f85`
- primary: `#1e66f5`
- accent: `#8839ef`
- success: `#40a02b`
- warning: `#df8e1d`
- danger: `#d20f39`

### 4. DFP Ayu Light

Slug: `dfp-ayu-light`

Personality: bright, airy, minimal, slightly golden.

Approximate colors:

- bg: `#fafafa`
- bg subtle: `#f3f4f5`
- surface: `#ffffff`
- surface raised: `#f8f9fa`
- border: `#e1e4e8`
- border strong: `#cfd7df`
- text: `#5c6773`
- muted text: `#828c99`
- primary: `#55b4d4`
- accent: `#f2ae49`
- success: `#86b300`
- warning: `#f2ae49`
- danger: `#f07178`

### 5. DFP Quiet Light

Slug: `dfp-quiet-light`

Personality: calm, gentle, low-distraction, professional.

Approximate colors:

- bg: `#f5f5f5`
- bg subtle: `#eeeeee`
- surface: `#ffffff`
- surface raised: `#f8f8f8`
- border: `#d7d7d7`
- border strong: `#bdbdbd`
- text: `#333333`
- muted text: `#6a6a6a`
- primary: `#007acc`
- accent: `#795e26`
- success: `#448c27`
- warning: `#b89500`
- danger: `#d12f1b`

### 6. DFP One Dark Pro

Slug: `dfp-one-dark-pro`

Personality: modern dark, professional, high contrast.

Approximate colors:

- bg: `#282c34`
- bg subtle: `#21252b`
- bg inset: `#1e2227`
- surface: `#2c313c`
- surface raised: `#353b45`
- border: `#3e4451`
- border strong: `#4b5263`
- text: `#abb2bf`
- muted text: `#7f848e`
- primary: `#61afef`
- accent: `#c678dd`
- success: `#98c379`
- warning: `#e5c07b`
- danger: `#e06c75`

### 7. DFP Dracula

Slug: `dfp-dracula`

Personality: bold, playful, dark purple, high-energy.

Approximate colors:

- bg: `#282a36`
- bg subtle: `#21222c`
- bg inset: `#191a21`
- surface: `#303241`
- surface raised: `#3a3c4e`
- border: `#44475a`
- border strong: `#6272a4`
- text: `#f8f8f2`
- muted text: `#bdc2d6`
- primary: `#bd93f9`
- accent: `#ff79c6`
- success: `#50fa7b`
- warning: `#f1fa8c`
- danger: `#ff5555`

### 8. DFP GitHub Dark

Slug: `dfp-github-dark`

Personality: practical, neutral, familiar dark mode.

Approximate colors:

- bg: `#0d1117`
- bg subtle: `#161b22`
- bg inset: `#010409`
- surface: `#161b22`
- surface raised: `#21262d`
- border: `#30363d`
- border strong: `#8b949e`
- text: `#c9d1d9`
- muted text: `#8b949e`
- primary: `#58a6ff`
- accent: `#bc8cff`
- success: `#3fb950`
- warning: `#d29922`
- danger: `#f85149`

### 9. DFP Tokyo Night

Slug: `dfp-tokyo-night`

Personality: deep navy, neon accents, modern night-dashboard feel.

Approximate colors:

- bg: `#1a1b26`
- bg subtle: `#16161e`
- bg inset: `#11111a`
- surface: `#24283b`
- surface raised: `#292e42`
- border: `#414868`
- border strong: `#565f89`
- text: `#c0caf5`
- muted text: `#a9b1d6`
- primary: `#7aa2f7`
- accent: `#bb9af7`
- success: `#9ece6a`
- warning: `#e0af68`
- danger: `#f7768e`

### 10. DFP Catppuccin Mocha

Slug: `dfp-catppuccin-mocha`

Personality: soft dark, warm pastel, friendly nighttime mode.

Approximate colors:

- bg: `#1e1e2e`
- bg subtle: `#181825`
- bg inset: `#11111b`
- surface: `#313244`
- surface raised: `#45475a`
- border: `#585b70`
- border strong: `#6c7086`
- text: `#cdd6f4`
- muted text: `#a6adc8`
- primary: `#89b4fa`
- accent: `#cba6f7`
- success: `#a6e3a1`
- warning: `#f9e2af`
- danger: `#f38ba8`

## Tailwind Requirements

Modify Tailwind configuration so utilities can reference theme variables.

Use semantic names, not raw colors, for app components.

Example Tailwind config colors:

```js
colors: {
  app: {
    bg: 'var(--color-bg)',
    subtle: 'var(--color-bg-subtle)',
    inset: 'var(--color-bg-inset)',
    surface: 'var(--color-surface)',
    raised: 'var(--color-surface-raised)',
    muted: 'var(--color-surface-muted)',
    border: 'var(--color-border)',
    text: 'var(--color-text)',
    soft: 'var(--color-text-soft)',
  },
  primary: {
    DEFAULT: 'var(--color-primary)',
    hover: 'var(--color-primary-hover)',
    active: 'var(--color-primary-active)',
    text: 'var(--color-primary-text)',
  },
  success: 'var(--color-success)',
  warning: 'var(--color-warning)',
  danger: 'var(--color-danger)',
  info: 'var(--color-info)',
}
```

Add CSS component classes in the app CSS so templates use reusable classes:

- `.app-shell`
- `.app-card`
- `.app-card-header`
- `.app-button`
- `.app-button-primary`
- `.app-button-secondary`
- `.app-button-danger`
- `.app-button-ghost`
- `.app-input`
- `.app-select`
- `.app-textarea`
- `.app-table`
- `.app-badge`
- `.app-badge-success`
- `.app-badge-warning`
- `.app-badge-danger`
- `.app-alert`
- `.app-modal`
- `.pos-shell`
- `.pos-product-tile`
- `.pos-category-button`
- `.pos-cart-panel`
- `.pos-checkout-button`

Do not scatter hardcoded Tailwind color classes like `bg-white`, `text-gray-900`, `border-gray-200`, `bg-blue-600`, or `dark:bg-gray-900` throughout templates. Replace existing hardcoded colors with semantic theme-aware classes.

Accept spacing/layout Tailwind utilities. Avoid raw color utilities unless truly necessary.

## Persistence Requirements

Theme selection must persist.

Implement:

1. App default theme setting.
2. Per-user preferred theme if logged in.
3. Anonymous/public user theme stored in localStorage.
4. Immediate theme switching without full page reload.
5. Server-side initial theme render to avoid flash of wrong theme.

Suggested database model:

```python
class UserPreference(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    theme_slug = db.Column(db.String(80), nullable=False, default='dfp-github-light')
    density = db.Column(db.String(30), nullable=False, default='comfortable')
    created_at = db.Column(db.DateTime, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False)
```

If the existing user/settings model already has a good place for this, use it instead of adding unnecessary tables.

Add app-level setting:

- `DEFAULT_THEME=dfp-github-light`

## Theme Settings UI

Create a settings page:

```text
/settings/themes
```

The page must include:

- Theme grid with all 10 themes.
- Live preview card for each theme.
- Label for Light or Dark.
- Short description/personality for each theme.
- Button to apply theme.
- Current theme indicator.
- Preview panel showing cards, buttons, inputs, badges, table row, alert, and POS tile.
- Optional reset-to-default button.

Admin users can choose the app default theme.

All logged-in users can choose their own preferred theme.

Anonymous users on public pages can choose a theme only if the app already has a public preference UI. If not, store anonymous theme only when they interact with the public theme toggle.

Add a compact theme toggle/dropdown in the header/navbar for logged-in users.

## POS Requirements

The POS must fully support the theme system.

The POS needs to look good and remain fast in every theme.

Theme tokens must affect:

- POS background.
- POS category sidebar/buttons.
- Product buttons/tiles.
- Product tile hover state.
- Product tile selected state if used.
- Cart panel.
- Cart item rows.
- Quantity controls.
- Cash checkout button.
- Card-processing placeholder button.
- Custom item button.
- Custom order/deposit button.
- Market session banner.
- Totals area.
- Payment confirmation modal.
- Change-due display.

Add theme previews that include a POS tile/card preview.

If POS is a Preact/Vite island, pass the active theme via `data-theme` on the root document and ensure the POS island consumes CSS variables rather than maintaining a separate theme system.

## Chart Requirements

Analytics charts must use theme variables.

Create a helper function or JS module that reads chart colors from CSS variables and applies them to Chart.js.

Required behavior:

- Charts update colors when theme changes.
- Axis/grid/tooltip colors follow theme.
- Chart series use `--chart-1` through `--chart-5`.
- Tooltips remain readable.

## Accessibility Requirements

Theme quality matters.

Do the following:

1. Check contrast for text/background, buttons, alerts, table text, badges, and POS checkout controls.
2. Adjust colors where needed to approximate WCAG AA for normal text.
3. Ensure keyboard focus rings are visible in every theme.
4. Do not rely on color alone for status badges. Use text labels/icons where appropriate.
5. Respect `prefers-reduced-motion`.
6. Respect `prefers-color-scheme` only for first-time default selection if no app/user preference exists.
7. Ensure print styles stay readable regardless of active theme.

## Backend Routes and API

Add settings routes:

```text
GET  /settings/themes
POST /settings/themes/apply
POST /settings/themes/default
```

Add API endpoints:

```text
GET   /api/v1/themes
GET   /api/v1/themes/current
PATCH /api/v1/users/me/theme
PATCH /api/v1/settings/default-theme
```

API responses should include:

- slug
- name
- mode: light/dark
- description
- tokens or token preview summary if safe/practical
- current user theme
- app default theme

Require authentication for user theme updates.
Require admin authorization for app default theme update.

## Migration Requirements

If adding database fields or tables:

1. Create a Flask-Migrate/Alembic migration.
2. Set default theme to `dfp-github-light`.
3. Backfill existing users if needed.
4. Ensure migration is reversible where practical.

## Template Refactor Requirements

Audit and update all relevant templates.

At minimum, theme these areas:

- base layout
- public layout/pages
- dashboard
- CRUD list pages
- CRUD create/edit forms
- product pages
- printer pages
- filament pages
- print job pages
- inventory pages
- customer pages
- order pages
- custom request pages
- market pages
- expense pages
- analytics pages
- settings pages
- POS pages
- auth/login pages
- error pages

Replace raw color classes with semantic component classes or CSS variables.

## Documentation Requirements

Update docs:

- README.md
- DESIGN.md if present
- docs/themes.md

Documentation must include:

1. How themes work.
2. How to add a new theme.
3. Full list of available theme slugs.
4. Token list.
5. How POS consumes theme tokens.
6. How charts consume theme tokens.
7. How user preference persistence works.

## Tests

Add tests for:

1. Theme registry contains 10 themes.
2. Each theme has all required tokens.
3. Theme settings page loads for authenticated users.
4. Applying a user theme persists.
5. Invalid theme slug is rejected.
6. API lists themes.
7. API updates current user theme.
8. Non-admin cannot update app default theme.
9. CSS file contains all required theme selectors.
10. POS route/page includes theme-aware root or consumes document theme.

## Acceptance Criteria

This phase is done only when:

- All 10 themes exist.
- All 10 themes define the required tokens.
- Theme selection persists for logged-in users.
- Public anonymous theme preference uses localStorage if exposed.
- App default theme can be managed by admin.
- Header theme switcher works.
- `/settings/themes` works.
- API theme endpoints work.
- Theme applies to public pages, admin pages, CRUD pages, analytics, and POS.
- Hardcoded colors are removed from major templates.
- POS checkout UI is usable in every theme.
- Chart.js charts use theme variables.
- Tests pass with `uv run pytest`.
- Lint/format checks pass.
- README/docs are updated.

## Build Instructions

Use uv.

Run:

```bash
uv lock
uv run flask db migrate -m "add theme preferences"
uv run flask db upgrade
uv run pytest
```

If frontend assets require build commands, run the appropriate npm/pnpm/uv task already used by this repo.

Do not introduce a heavy frontend framework for this phase.
Do not convert the whole app to a SPA.
Do not create a second competing theme system for POS.
Do not store theme as a browser-only setting for logged-in users.
Do not hardcode colors in individual templates when a token/component class should be used.

Before finishing, provide:

1. Summary of files changed.
2. Theme slugs added.
3. How to test the theme switcher.
4. How to add another theme later.
5. Any remaining color hardcoding that could not safely be removed.
