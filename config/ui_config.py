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
        "top_y": 48,
        "align_x": "center",
        "offset_x": 0,
    },
    "dimensions": {
        "compact_width": 224,
        "compact_height": 40,
        "expanded_width": 480,
        "expanded_height": 520,
        "pill_gap": 7,
    },
    "colors": {
        "surface_top": "#141726",
        "surface_bottom": "#0D1019",
        "surface_border": "rgba(120, 146, 255, 0.16)",
        "capsule_top": "#262E44",
        "capsule_bottom": "#181E2E",
        "capsule_hover_top": "#303B56",
        "capsule_hover_bottom": "#1F273C",
        "capsule_border": "rgba(120, 146, 255, 0.20)",
        "capsule_border_hover": "rgba(142, 165, 255, 0.35)",
        "user_bubble_start": "#314E85",
        "user_bubble_end": "#243860",
        "user_bubble_border": "rgba(120, 146, 255, 0.25)",
        "assistant_bubble_start": "#1C2333",
        "assistant_bubble_end": "#151A26",
        "assistant_bubble_border": "rgba(120, 146, 255, 0.15)",
        "composer_top": "#1E2536",
        "composer_bottom": "#151B27",
        "composer_border": "rgba(120, 146, 255, 0.22)",
        "accent_blue": "#7892FF",
        "accent_blue_hover": "#8EA5FF",
        "accent_green": "#58D6A0",
        "accent_amber": "#FFB300",
        "accent_red": "#FF4444",
        "text_primary": "#E5E9F2",
        "text_secondary": "#9BAAC5",
        "text_muted": "#6B7B99",
    },
    "fonts": {
        "family": "JetBrainsMono Nerd Font",
        "bold": True,
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

