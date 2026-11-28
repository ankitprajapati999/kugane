# -*- coding: utf-8 -*-
"""
core/agents/tools/vision_tools.py — Astra-style Live Screen Capture & Vision Tools.

Allows Kugane's VisionAgent to capture the user's current screen and analyze
active applications, 3D viewports, errors, or references using the active VLM/LLM.
"""
from __future__ import annotations

import base64
import json
import time
from io import BytesIO
from pathlib import Path
from typing import Callable, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from config.settings import GENERATED_WORKSPACE

_VISION_DIR = GENERATED_WORKSPACE / "vision"
_MODEL_GETTER: Optional[Callable[[], Optional[BaseChatModel]]] = None


def set_vision_model_getter(getter: Callable[[], Optional[BaseChatModel]]) -> None:
    """Register the active chat/VLM model getter used by inspect_screen_with_vlm."""
    global _MODEL_GETTER
    _MODEL_GETTER = getter


def capture_screen_file(save_name: str = "screen_latest.png", max_width: int = 1600) -> dict:
    """Capture the primary monitor to disk and return metadata + base64 JPEG/PNG."""
    import mss
    from PIL import Image

    _VISION_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = Path(save_name).name or "screen_latest.png"
    out_path = _VISION_DIR / safe_name

    with mss.mss() as sct:
        monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        raw = sct.grab(monitor)
        img = Image.frombytes("RGB", raw.size, raw.rgb)

    if img.width > max_width:
        ratio = max_width / float(img.width)
        img = img.resize((max_width, max(1, int(img.height * ratio))), Image.Resampling.LANCZOS)

    img.save(out_path, format="PNG")
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=82)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    return {
        "image_path": str(out_path),
        "width": img.width,
        "height": img.height,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "base64_jpeg": b64,
    }


@tool
def capture_current_screen(save_name: str = "screen_latest.png") -> str:
    """
    Capture a screenshot of the user's current Windows desktop screen and save it
    to the Kugane workspace. Returns JSON with image_path, dimensions, and timestamp.
    """
    info = capture_screen_file(save_name=save_name)
    return json.dumps(
        {
            "status": "captured",
            "image_path": info["image_path"],
            "width": info["width"],
            "height": info["height"],
            "timestamp": info["timestamp"],
        },
        indent=2,
    )


@tool
def inspect_screen_with_vlm(
    question: str = "Describe what is currently on the user's screen, including open apps, 3D scenes, code, or errors.",
) -> str:
    """
    Capture the user's current screen and inspect it using the active VLM/LLM
    (Gemini or connected Flask VLM server) to answer a visual question about
    what the user is looking at right now.
    """
    info = capture_screen_file("screen_inspect.png")
    model = _MODEL_GETTER() if _MODEL_GETTER is not None else None
    if model is None:
        return json.dumps(
            {
                "status": "captured_no_model",
                "image_path": info["image_path"],
                "note": "Screen captured, but no VLM/LLM is initialised to analyze it.",
            }
        )

    msg = HumanMessage(
        content=[
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{info['base64_jpeg']}"},
            },
            {
                "type": "text",
                "text": (
                    "You are inspecting a live screenshot of the user's Windows screen.\n"
                    f"Question: {question}"
                ),
            },
        ]
    )
    resp = model.invoke([msg])
    answer = resp.content if isinstance(resp.content, str) else str(resp.content)
    return json.dumps(
        {
            "status": "analyzed",
            "image_path": info["image_path"],
            "analysis": answer.strip(),
        },
        indent=2,
    )
