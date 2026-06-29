"""Markdown rendering configuration.

Edit this file to customize the look and feel of rendered Markdown content.
Each key maps to a CSS rule injected via a <style> tag with a scoped class.

The rendered HTML is wrapped in a div with class "md-render".
"""

import re
from typing import Any

import markdown as md_lib


DEFAULT_CONFIG: dict[str, dict[str, str]] = {
    # ── Font Families ──────────────────────────────────────────────
    "font_family": {
        "body": (
            "'Inter', system-ui, -apple-system, BlinkMacSystemFont, "
            "'Segoe UI', Roboto, sans-serif"
        ),
        "headings": (
            "'Inter', system-ui, -apple-system, BlinkMacSystemFont, "
            "'Segoe UI', Roboto, sans-serif"
        ),
        "code": "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
    },
    # ── Heading Sizes ──────────────────────────────────────────────
    "heading_sizes": {
        "h1": "1.75rem",
        "h2": "1.35rem",
        "h3": "1.15rem",
        "h4": "1.05rem",
        "h5": "1rem",
        "h6": "0.9rem",
    },
    "heading_weights": {
        "h1": "700",
        "h2": "600",
        "h3": "600",
        "h4": "600",
        "h5": "600",
        "h6": "600",
    },
    # ── Body Text ──────────────────────────────────────────────────
    "body_size": "0.95rem",
    "body_line_height": "1.65",
    "body_color": "var(--color-text, #1f2937)",
    # ── Paragraph Spacing ──────────────────────────────────────────
    "paragraph_margin_bottom": "0.75em",
    "paragraph_line_height": "1.65",
    # ── Lists ──────────────────────────────────────────────────────
    "list_padding_left": "1.5em",
    "list_margin_bottom": "0.75em",
    "list_item_margin_bottom": "0.3em",
    # ── Code Blocks ────────────────────────────────────────────────
    "code_block_bg": "var(--color-surface-alt, #f3f4f6)",
    "code_block_border_radius": "6px",
    "code_block_padding": "0.8em 1em",
    "code_block_font_size": "0.85rem",
    "code_block_line_height": "1.5",
    "inline_code_bg": "var(--color-surface-alt, #f3f4f6)",
    "inline_code_padding": "0.15em 0.4em",
    "inline_code_border_radius": "4px",
    "inline_code_font_size": "0.85em",
    # ── Blockquotes ────────────────────────────────────────────────
    "blockquote_border_left": "4px solid var(--color-primary, #f97316)",
    "blockquote_bg": "var(--color-surface, #fafafa)",
    "blockquote_padding": "0.5em 1em",
    "blockquote_margin": "1em 0",
    "blockquote_font_style": "italic",
    # ── Horizontal Rules ───────────────────────────────────────────
    "hr_margin": "1.5em 0",
    "hr_border": "1px solid var(--color-border, #e5e7eb)",
    # ── Links ──────────────────────────────────────────────────────
    "link_color": "var(--color-primary, #f97316)",
    "link_decoration": "underline",
    "link_hover_color": "var(--color-primary-hover, #ea580c)",
    # ── Tables ─────────────────────────────────────────────────────
    "table_width": "100%",
    "table_border_collapse": "collapse",
    "table_margin": "1em 0",
    "table_header_bg": "var(--color-surface-alt, #f3f4f6)",
    "table_header_font_weight": "600",
    "table_cell_padding": "0.5em 0.75em",
    "table_cell_border": "1px solid var(--color-border, #e5e7eb)",
    "table_row_alt_bg": "var(--color-surface, #fafafa)",
    # ── Strong / Emphasis ──────────────────────────────────────────
    "strong_font_weight": "600",
    "emphasis_font_style": "italic",
    # ── Dividers / Spacing ─────────────────────────────────────────
    "heading_margin_top": "1.5em",
    "heading_margin_bottom": "0.5em",
}

# ── Markdown extras (Python-Markdown extensions) ───────────────
MARKDOWN_EXTENSIONS = [
    "extra",
    "codehilite",
    "toc",
    "sane_lists",
]


def build_config_css(overrides: dict[str, Any] | None = None) -> str:
    """Generate a CSS string from the config dict, optionally overridden."""
    cfg = {**DEFAULT_CONFIG, **(overrides or {})}
    ff = cfg.get("font_family", {})
    hs = cfg.get("heading_sizes", {})
    hw = cfg.get("heading_weights", {})

    lines: list[str] = [
        ".md-render {",
        f"  font-family: {ff.get('body', DEFAULT_CONFIG['font_family']['body'])};",
        f"  font-size: {cfg.get('body_size', DEFAULT_CONFIG['body_size'])};",
        f"  line-height: {cfg.get('body_line_height', DEFAULT_CONFIG['body_line_height'])};",
        f"  color: {cfg.get('body_color', DEFAULT_CONFIG['body_color'])};",
        "}",
    ]

    for tag in ["h1", "h2", "h3", "h4", "h5", "h6"]:
        size = hs.get(tag, DEFAULT_CONFIG["heading_sizes"].get(tag, "1rem"))
        weight = hw.get(tag, DEFAULT_CONFIG["heading_weights"].get(tag, "600"))
        lines.append(f".md-render {tag} {{")
        lines.append(f"  font-family: {ff.get('headings', ff['body'])};")
        lines.append(f"  font-size: {size};")
        lines.append(f"  font-weight: {weight};")
        lines.append(
            f"  margin-top: {cfg.get('heading_margin_top', DEFAULT_CONFIG['heading_margin_top'])};"
        )
        lines.append(
            f"  margin-bottom: {cfg.get('heading_margin_bottom', DEFAULT_CONFIG['heading_margin_bottom'])};"
        )
        lines.append("}")

    lines.append(".md-render p {")
    lines.append(
        f"  margin-bottom: {cfg.get('paragraph_margin_bottom', DEFAULT_CONFIG['paragraph_margin_bottom'])};"
    )
    lines.append(
        f"  line-height: {cfg.get('paragraph_line_height', DEFAULT_CONFIG['paragraph_line_height'])};"
    )
    lines.append("}")

    lines.append(".md-render ul, .md-render ol {")
    lines.append(
        f"  padding-left: {cfg.get('list_padding_left', DEFAULT_CONFIG['list_padding_left'])};"
    )
    lines.append(
        f"  margin-bottom: {cfg.get('list_margin_bottom', DEFAULT_CONFIG['list_margin_bottom'])};"
    )
    lines.append("}")
    lines.append(".md-render li {")
    lines.append(
        f"  margin-bottom: {cfg.get('list_item_margin_bottom', DEFAULT_CONFIG['list_item_margin_bottom'])};"
    )
    lines.append("}")

    lines.append(".md-render pre {")
    lines.append(
        f"  background-color: {cfg.get('code_block_bg', DEFAULT_CONFIG['code_block_bg'])};"
    )
    lines.append(
        f"  border-radius: {cfg.get('code_block_border_radius', DEFAULT_CONFIG['code_block_border_radius'])};"
    )
    lines.append(
        f"  padding: {cfg.get('code_block_padding', DEFAULT_CONFIG['code_block_padding'])};"
    )
    lines.append(
        f"  font-size: {cfg.get('code_block_font_size', DEFAULT_CONFIG['code_block_font_size'])};"
    )
    lines.append(
        f"  line-height: {cfg.get('code_block_line_height', DEFAULT_CONFIG['code_block_line_height'])};"
    )
    lines.append(
        f"  font-family: {ff.get('code', DEFAULT_CONFIG['font_family']['code'])};"
    )
    lines.append("  overflow-x: auto;")
    lines.append("}")
    lines.append(".md-render code {")
    lines.append(
        f"  font-family: {ff.get('code', DEFAULT_CONFIG['font_family']['code'])};"
    )
    lines.append(
        f"  font-size: {cfg.get('inline_code_font_size', DEFAULT_CONFIG['inline_code_font_size'])};"
    )
    lines.append("}")
    lines.append(".md-render :not(pre) > code {")
    lines.append(
        f"  background-color: {cfg.get('inline_code_bg', DEFAULT_CONFIG['inline_code_bg'])};"
    )
    lines.append(
        f"  padding: {cfg.get('inline_code_padding', DEFAULT_CONFIG['inline_code_padding'])};"
    )
    lines.append(
        f"  border-radius: {cfg.get('inline_code_border_radius', DEFAULT_CONFIG['inline_code_border_radius'])};"
    )
    lines.append("}")

    lines.append(".md-render blockquote {")
    lines.append(
        f"  border-left: {cfg.get('blockquote_border_left', DEFAULT_CONFIG['blockquote_border_left'])};"
    )
    lines.append(
        f"  background-color: {cfg.get('blockquote_bg', DEFAULT_CONFIG['blockquote_bg'])};"
    )
    lines.append(
        f"  padding: {cfg.get('blockquote_padding', DEFAULT_CONFIG['blockquote_padding'])};"
    )
    lines.append(
        f"  margin: {cfg.get('blockquote_margin', DEFAULT_CONFIG['blockquote_margin'])};"
    )
    lines.append(
        f"  font-style: {cfg.get('blockquote_font_style', DEFAULT_CONFIG['blockquote_font_style'])};"
    )
    lines.append("}")

    lines.append(".md-render hr {")
    lines.append(
        f"  margin: {cfg.get('hr_margin', DEFAULT_CONFIG['hr_margin'])};"
    )
    lines.append(
        f"  border: {cfg.get('hr_border', DEFAULT_CONFIG['hr_border'])};"
    )
    lines.append("}")

    lines.append(".md-render a {")
    lines.append(
        f"  color: {cfg.get('link_color', DEFAULT_CONFIG['link_color'])};"
    )
    lines.append(
        f"  text-decoration: {cfg.get('link_decoration', DEFAULT_CONFIG['link_decoration'])};"
    )
    lines.append("}")
    lines.append(".md-render a:hover {")
    lines.append(
        f"  color: {cfg.get('link_hover_color', DEFAULT_CONFIG['link_hover_color'])};"
    )
    lines.append("}")

    lines.append(".md-render table {")
    lines.append(
        f"  width: {cfg.get('table_width', DEFAULT_CONFIG['table_width'])};"
    )
    lines.append(
        f"  border-collapse: {cfg.get('table_border_collapse', DEFAULT_CONFIG['table_border_collapse'])};"
    )
    lines.append(
        f"  margin: {cfg.get('table_margin', DEFAULT_CONFIG['table_margin'])};"
    )
    lines.append("}")
    lines.append(".md-render th {")
    lines.append(
        f"  background-color: {cfg.get('table_header_bg', DEFAULT_CONFIG['table_header_bg'])};"
    )
    lines.append(
        f"  font-weight: {cfg.get('table_header_font_weight', DEFAULT_CONFIG['table_header_font_weight'])};"
    )
    lines.append(
        f"  padding: {cfg.get('table_cell_padding', DEFAULT_CONFIG['table_cell_padding'])};"
    )
    lines.append(
        f"  border: {cfg.get('table_cell_border', DEFAULT_CONFIG['table_cell_border'])};"
    )
    lines.append("}")
    lines.append(".md-render td {")
    lines.append(
        f"  padding: {cfg.get('table_cell_padding', DEFAULT_CONFIG['table_cell_padding'])};"
    )
    lines.append(
        f"  border: {cfg.get('table_cell_border', DEFAULT_CONFIG['table_cell_border'])};"
    )
    lines.append("}")
    lines.append(".md-render tr:nth-child(even) {")
    lines.append(
        f"  background-color: {cfg.get('table_row_alt_bg', DEFAULT_CONFIG['table_row_alt_bg'])};"
    )
    lines.append("}")

    lines.append(
        f".md-render strong {{ font-weight: {cfg.get('strong_font_weight', DEFAULT_CONFIG['strong_font_weight'])}; }}"
    )
    lines.append(
        f".md-render em {{ font-style: {cfg.get('emphasis_font_style', DEFAULT_CONFIG['emphasis_font_style'])}; }}"
    )

    return "\n".join(lines)


def render_markdown(text: str, css_overrides: dict[str, Any] | None = None) -> str:
    """Render Markdown text to styled HTML."""
    html_body = md_lib.markdown(
        text or "",
        extensions=MARKDOWN_EXTENSIONS,
        extension_configs={
            "codehilite": {"css_class": "highlight"},
        },
    )
    css = build_config_css(css_overrides)
    return (
        "<style>\n"
        f"{css}\n"
        "</style>\n"
        f'<div class="md-render">\n{html_body}\n</div>'
    )
