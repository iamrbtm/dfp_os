from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Theme:
    slug: str
    name: str
    mode: str  # "light" or "dark"
    description: str
    tokens: dict[str, str] = field(default_factory=dict)


LIGHT_THEMES = [
    Theme(
        slug="dfp-github-light",
        name="DFP GitHub Light",
        mode="light",
        description="Clean, neutral, familiar, businesslike.",
    ),
    Theme(
        slug="dfp-atom-one-light",
        name="DFP Atom One Light",
        mode="light",
        description="Soft white, readable, code-editor clean.",
    ),
    Theme(
        slug="dfp-catppuccin-latte",
        name="DFP Catppuccin Latte",
        mode="light",
        description="Warm pastel, friendly, soft, modern.",
    ),
    Theme(
        slug="dfp-ayu-light",
        name="DFP Ayu Light",
        mode="light",
        description="Bright, airy, minimal, slightly golden.",
    ),
    Theme(
        slug="dfp-quiet-light",
        name="DFP Quiet Light",
        mode="light",
        description="Calm, gentle, low-distraction, professional.",
    ),
]

DARK_THEMES = [
    Theme(
        slug="dfp-one-dark-pro",
        name="DFP One Dark Pro",
        mode="dark",
        description="Modern dark, professional, high contrast.",
    ),
    Theme(
        slug="dfp-dracula",
        name="DFP Dracula",
        mode="dark",
        description="Bold, playful, dark purple, high-energy.",
    ),
    Theme(
        slug="dfp-github-dark",
        name="DFP GitHub Dark",
        mode="dark",
        description="Practical, neutral, familiar dark mode.",
    ),
    Theme(
        slug="dfp-tokyo-night",
        name="DFP Tokyo Night",
        mode="dark",
        description="Deep navy, neon accents, modern night-dashboard feel.",
    ),
    Theme(
        slug="dfp-catppuccin-mocha",
        name="DFP Catppuccin Mocha",
        mode="dark",
        description="Soft dark, warm pastel, friendly nighttime mode.",
    ),
]

ALL_THEMES = LIGHT_THEMES + DARK_THEMES
THEME_MAP = {t.slug: t for t in ALL_THEMES}

DEFAULT_THEME = "dfp-github-light"

REQUIRED_TOKENS = [
    "color-bg",
    "color-bg-subtle",
    "color-bg-inset",
    "color-surface",
    "color-surface-raised",
    "color-surface-muted",
    "color-border",
    "color-border-strong",
    "color-divider",
    "color-text",
    "color-text-muted",
    "color-text-soft",
    "color-text-inverted",
    "color-link",
    "color-link-hover",
    "color-primary",
    "color-primary-hover",
    "color-primary-active",
    "color-primary-text",
    "color-secondary",
    "color-secondary-hover",
    "color-secondary-text",
    "color-accent",
    "color-accent-hover",
    "color-accent-text",
    "color-success",
    "color-success-bg",
    "color-warning",
    "color-warning-bg",
    "color-danger",
    "color-danger-bg",
    "color-info",
    "color-info-bg",
    "color-input-bg",
    "color-input-border",
    "color-input-text",
    "color-input-placeholder",
    "color-input-focus",
    "color-checkbox-bg",
    "color-checkbox-border",
    "color-button-border",
    "color-button-ghost-hover",
    "color-button-disabled-bg",
    "color-button-disabled-text",
    "color-table-header",
    "color-table-row-hover",
    "color-table-selected",
    "color-table-border",
    "color-nav-bg",
    "color-nav-border",
    "color-nav-text",
    "color-nav-muted",
    "color-nav-active-bg",
    "color-nav-active-text",
    "color-sidebar-bg",
    "color-sidebar-border",
    "color-sidebar-text",
    "color-sidebar-muted",
    "color-sidebar-active-bg",
    "color-sidebar-active-text",
    "color-pos-bg",
    "color-pos-toolbar-bg",
    "color-pos-tile-bg",
    "color-pos-tile-border",
    "color-pos-tile-hover",
    "color-pos-tile-text",
    "color-pos-category-bg",
    "color-pos-category-active-bg",
    "color-pos-cart-bg",
    "color-pos-cart-border",
    "color-pos-checkout-bg",
    "color-pos-checkout-hover",
    "color-pos-checkout-text",
    "color-pos-cash-bg",
    "color-pos-card-placeholder-bg",
    "chart-1",
    "chart-2",
    "chart-3",
    "chart-4",
    "chart-5",
    "chart-grid",
    "chart-axis",
    "chart-tooltip-bg",
    "chart-tooltip-text",
    "color-focus-ring",
    "shadow-card",
    "shadow-popover",
    "radius-sm",
    "radius-md",
    "radius-lg",
]


def is_valid_theme(slug: str) -> bool:
    return slug in THEME_MAP


def get_theme(slug: str) -> Theme | None:
    return THEME_MAP.get(slug)
