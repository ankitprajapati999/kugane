# -*- coding: utf-8 -*-
"""
config/ui_config.py — Kugane UI Configuration Loader.

Loads layout dimensions, positioning, colors, and font preferences from
config/ui_config.yaml with graceful fallback to built-in defaults.
"""
from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Any, Dict

import yaml

log = logging.getLogger(__name__)

_DEFAULT_CONFIG: Dict[str, Any] = {
    "position": {
        "top_y": 0,
        "align_x": "center",
        "offset_x": 0,
    },
    "dimensions": {
        "compact_width_inches": 4.7,
        "compact_height_inches": 0.525,
        "compact_width": 427,
        "compact_height": 48,
        "expanded_width": 480,
        "expanded_height": 520,
        "min_expanded_width": 360,
        "min_expanded_height": 320,
        "ear_radius": 14,
        "compact_bottom_radius": 18,
        "expanded_bottom_radius": 28,
    },
    "colors": {
        "notch_bg": "#000000",
        "notch_border": "rgba(255, 255, 255, 0.14)",
        "notch_border_hover": "rgba(185, 188, 198, 0.56)",
        "user_bubble_start": "#1B1B20",
        "user_bubble_end": "#141418",
        "user_bubble_border": "rgba(255, 212, 0, 0.25)",
        "assistant_bubble_start": "#0F0F12",
        "assistant_bubble_end": "#09090B",
        "assistant_bubble_border": "rgba(255, 255, 255, 0.10)",
        "composer_top": "#111115",
        "composer_bottom": "#0A0A0D",
        "composer_border": "rgba(255, 255, 255, 0.14)",
        "accent_primary": "#FFD400",
        "accent_primary_hover": "#FFE033",
        "accent_blue": "#FFD400",
        "accent_blue_hover": "#FFE033",
        "accent_green": "#32D74B",
        "accent_amber": "#FF9F0A",
        "accent_red": "#FF453A",
        "text_primary": "#FFFFFF",
        "text_secondary": "#98989F",
        "text_muted": "#636369",
    },
    "fonts": {
        "family": "Poppins",
        "fallback_family": "Outfit",
        "bold": False,
    },
}

_CONFIG_PATH = Path(__file__).resolve().parent / "ui_config.yaml"


def _recursive_merge(base: dict, overlay: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and k in out and isinstance(out[k], dict):
            out[k] = _recursive_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_ui_config(config_file: Path | None = None) -> dict:
    """Loads and validates UI configuration from YAML, falling back to defaults."""
    target_path = config_file or _CONFIG_PATH
    config = copy.deepcopy(_DEFAULT_CONFIG)

    if not target_path.exists():
        log.warning("UI config file %s not found, using defaults", target_path)
        return config

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)
        if isinstance(raw_data, dict):
            config = _recursive_merge(config, raw_data)
            log.info("UI config loaded from %s", target_path)
        else:
            log.warning("Invalid format in %s, using defaults", target_path)
    except Exception as exc:
        log.warning("Error reading %s: %s; using defaults", target_path, exc)

    return config

