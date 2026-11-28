# -*- coding: utf-8 -*-
"""
ui/theme.py — Kugane UI Theme Tokens, Color Helpers & Notch Path Geometry.

Reads user-tweakable settings from config/ui_config.yaml and exposes shared
design tokens and geometry helpers used across all UI modules.
"""
from __future__ import annotations

import re
from pathlib import Path

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QFont, QPainterPath

from config.ui_config import load_ui_config as _load_ui_config

UI_CONFIG = _load_ui_config()
COLORS = UI_CONFIG["colors"]
DIMENSIONS = UI_CONFIG["dimensions"]
POSITION = UI_CONFIG["position"]
FONTS = UI_CONFIG["fonts"]

ASSETS_DIR = Path(__file__).resolve().parent / "Assets"
LOGO_PATH = ASSETS_DIR / "Final Logo.png"


def parse_color(value: str, fallback: str = "#000000") -> QColor:
    """Parse hex or rgb/rgba CSS color strings into QColor."""
    raw = (value or fallback).strip()
    m = re.match(
        r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([0-9.]+)\s*)?\)",
        raw,
        re.IGNORECASE,
    )
    if m:
        r, g, b = int(m.group(1)), int(m.group(2)), int(m.group(3))
        a_raw = m.group(4)
        a = int(float(a_raw) * 255) if a_raw is not None else 255
        if a_raw is not None and float(a_raw) > 1.0:
            a = int(float(a_raw))
        return QColor(r, g, b, max(0, min(255, a)))
    c = QColor(raw)
    return c if c.isValid() else QColor(fallback)


# ── Design System Tokens ──────────────────────────────────────────────────────
NOTCH_BG              = COLORS.get("notch_bg", "#000000")
NOTCH_BORDER          = COLORS.get("notch_border", "rgba(255, 255, 255, 0.14)")
NOTCH_BORDER_HOVER    = COLORS.get("notch_border_hover", "rgba(185, 188, 198, 0.56)")

USER_BUBBLE_START     = COLORS.get("user_bubble_start", "#1B1B20")
USER_BUBBLE_END       = COLORS.get("user_bubble_end", "#141418")
USER_BUBBLE_BORDER    = COLORS.get("user_bubble_border", "rgba(255, 212, 0, 0.25)")

AI_BUBBLE_START       = COLORS.get("assistant_bubble_start", "#0F0F12")
AI_BUBBLE_END         = COLORS.get("assistant_bubble_end", "#09090B")
AI_BUBBLE_BORDER      = COLORS.get("assistant_bubble_border", "rgba(255, 255, 255, 0.10)")

COMPOSER_TOP          = COLORS.get("composer_top", "#111115")
COMPOSER_BOTTOM       = COLORS.get("composer_bottom", "#0A0A0D")
COMPOSER_BORDER       = COLORS.get("composer_border", "rgba(255, 255, 255, 0.14)")

ACCENT_PRIMARY        = COLORS.get("accent_primary", COLORS.get("accent_blue", "#FFD400"))
ACCENT_PRIMARY_HOVER  = COLORS.get("accent_primary_hover", COLORS.get("accent_blue_hover", "#FFE033"))
ACCENT_GREEN          = COLORS.get("accent_green", "#32D74B")
ACCENT_AMBER          = COLORS.get("accent_amber", "#FF9F0A")
ACCENT_RED            = COLORS.get("accent_red", "#FF453A")

TEXT_PRIMARY          = COLORS.get("text_primary", "#FFFFFF")
TEXT_SECONDARY        = COLORS.get("text_secondary", "#98989F")
TEXT_MUTED            = COLORS.get("text_muted", "#636369")

FONT_FAMILY_PRIMARY   = FONTS.get("family", "Poppins")
FONT_FAMILY_FALLBACK  = FONTS.get("fallback_family", "Outfit")
FONT_FAMILY_SANS      = FONT_FAMILY_PRIMARY
FONT_FAMILY_MONO      = FONT_FAMILY_FALLBACK


def make_font(
    size: float,
    weight: QFont.Weight = QFont.Weight.Normal,
) -> QFont:
    """Create a clean Poppins/Outfit sans-serif font with subtle weight."""
    font = QFont()
    font.setFamilies([
        FONT_FAMILY_PRIMARY,
        FONT_FAMILY_FALLBACK,
        "Segoe UI Variable Text",
        "Segoe UI",
    ])
    font.setStyleHint(QFont.StyleHint.SansSerif)
    font.setPointSizeF(float(size))
    font.setWeight(weight)
    return font


def build_notch_paths(
    w: float,
    h: float,
    ear_r: float,
    bot_r: float,
) -> tuple[QPainterPath, QPainterPath]:
    """
    Build the top-attached notch silhouette with concave top ears and rounded bottom.

    Returns:
      (fill_path, open_border_path)
    where open_border_path omits the top y=0 segment so the notch merges into
    the upper bezel of the display.
    """
    ear = max(4.0, min(ear_r, w / 6.0, h / 3.0))
    inner_w = max(4.0, w - 2.0 * ear)
    bot = max(4.0, min(bot_r, inner_w / 2.0 - 1.0, max(4.0, h - ear - 1.0)))

    fill = QPainterPath()
    fill.moveTo(0.0, 0.0)
    fill.lineTo(w, 0.0)
    fill.arcTo(QRectF(w - ear, 0.0, 2.0 * ear, 2.0 * ear), 90.0, 90.0)
    fill.lineTo(w - ear, h - bot)
    fill.arcTo(
        QRectF(w - ear - 2.0 * bot, h - 2.0 * bot, 2.0 * bot, 2.0 * bot),
        0.0,
        -90.0,
    )
    fill.lineTo(ear + bot, h)
    fill.arcTo(QRectF(ear, h - 2.0 * bot, 2.0 * bot, 2.0 * bot), 270.0, -90.0)
    fill.lineTo(ear, ear)
    fill.arcTo(QRectF(-ear, 0.0, 2.0 * ear, 2.0 * ear), 0.0, 90.0)
    fill.closeSubpath()

    stroke = QPainterPath()
    stroke.moveTo(0.0, 0.0)
    stroke.arcTo(QRectF(-ear, 0.0, 2.0 * ear, 2.0 * ear), 90.0, -90.0)
    stroke.lineTo(ear, h - bot)
    stroke.arcTo(QRectF(ear, h - 2.0 * bot, 2.0 * bot, 2.0 * bot), 180.0, 90.0)
    stroke.lineTo(w - ear - bot, h)
    stroke.arcTo(
        QRectF(w - ear - 2.0 * bot, h - 2.0 * bot, 2.0 * bot, 2.0 * bot),
        270.0,
        90.0,
    )
    stroke.lineTo(w - ear, ear)
    stroke.arcTo(QRectF(w - ear, 0.0, 2.0 * ear, 2.0 * ear), 180.0, -90.0)

    return fill, stroke
