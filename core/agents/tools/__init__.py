# -*- coding: utf-8 -*-
"""core/agents/tools — Modular tool suites for Vision, Blender 3D, and Unity/Unreal."""

from core.agents.tools.vision_tools import (
    capture_current_screen,
    inspect_screen_with_vlm,
    set_vision_model_getter,
)
from core.agents.tools.blender_tools import (
    detect_blender,
    create_blender_model_script,
    run_blender_script,
    verify_blender_model_against_requirements,
    open_blender_model_gui,
    save_blender_model_keep_safe,
    list_stored_blender_models,
    set_blender_model_getter,
)
from core.agents.tools.engine_tools import (
    detect_game_engines,
    setup_unity_scene_and_mechanics,
    setup_unreal_scene_and_mechanics,
)

__all__ = [
    "capture_current_screen",
    "inspect_screen_with_vlm",
    "set_vision_model_getter",
    "detect_blender",
    "create_blender_model_script",
    "run_blender_script",
    "verify_blender_model_against_requirements",
    "open_blender_model_gui",
    "save_blender_model_keep_safe",
    "list_stored_blender_models",
    "set_blender_model_getter",
    "detect_game_engines",
    "setup_unity_scene_and_mechanics",
    "setup_unreal_scene_and_mechanics",
]
