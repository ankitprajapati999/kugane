# -*- coding: utf-8 -*-
"""
core/agents/orchestrator.py — LangChain Multi-Agent Supervisor Orchestrator.

Coordinates:
  - Supervisor       : Plans tasks, delegates to specialist agents, remembers session context
  - VisionAgent      : Captures & inspects current Windows screen (Astra-style live context)
  - BlenderAgent     : Generates & runs Blender bpy scripts to create/export 3D models
  - GameEngineAgent  : Imports models into Unity or Unreal and adds gameplay mechanics

Supports swappable LLM/VLM backends (Gemini API or remote laptop Flask VLM server)
via core.llm.providers.build_chat_model and streams live AgentProgressEvent updates
so the UI shows the user exactly what Kugane and each agent are doing.
"""
from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from core.agents.tools import (
    capture_current_screen,
    create_blender_model_script,
    detect_blender,
    detect_game_engines,
    inspect_screen_with_vlm,
    list_stored_blender_models,
    open_blender_model_gui,
    run_blender_script,
    save_blender_model_keep_safe,
    set_blender_model_getter,
    set_vision_model_getter,
    setup_unity_scene_and_mechanics,
    setup_unreal_scene_and_mechanics,
    verify_blender_model_against_requirements,
)
from core.agents.tools.vision_tools import capture_screen_file
from core.llm.providers import ProviderConfigError, build_chat_model
from core.media.file_processor import FileProcessor

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentProgressEvent:
    """Live progress update emitted during multi-agent orchestration."""

    agent: str
    title: str
    detail: str = ""
    status: str = "running"  # "running" | "done" | "error"


ProgressCallback = Callable[[AgentProgressEvent], None]


def _extract_text_from_message(msg: BaseMessage) -> str:
    content = msg.content
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "\n".join(p for p in parts if p).strip()
    return str(content).strip()


def _friendly_tool_title(tool_name: str) -> str:
    mapping = {
        "capture_current_screen": "Capturing desktop screen",
        "inspect_screen_with_vlm": "Analyzing screen with VLM",
        "detect_blender": "Checking Blender installation",
        "create_blender_model_script": "Writing realistic Blender 3D script",
        "run_blender_script": "Building 3D model in Blender",
        "verify_blender_model_against_requirements": "Verifying model accuracy vs requirements",
        "open_blender_model_gui": "Opening verified model in Blender",
        "save_blender_model_keep_safe": "Saving Blender model safely",
        "list_stored_blender_models": "Checking stored Blender models",
        "detect_game_engines": "Checking Unity & Unreal Engine",
        "setup_unity_scene_and_mechanics": "Setting up Unity scene & C# mechanics",
        "setup_unreal_scene_and_mechanics": "Setting up Unreal scene & mechanics",
        "delegate_to_vision_agent": "Delegating to VisionAgent",
        "delegate_to_blender_agent": "Delegating to BlenderAgent",
        "delegate_to_game_engine_agent": "Delegating to GameEngineAgent",
    }
    return mapping.get(tool_name, f"Running {tool_name}")


class MultiAgentOrchestrator:
    """
    Hierarchical LangChain multi-agent orchestrator with live progress streaming.
    """

    def __init__(
        self,
        provider: str = "gemini",
        api_key: str = "",
        model: str = "gemini-3.5-flash-lite",
        flask_url: str = "http://127.0.0.1:5000/chat",
        flask_timeout: float = 120.0,
        flask_api_key: str = "",
        system_instruction: str = "",
        history_max_turns: int = 40,
        chat_model: Optional[BaseChatModel] = None,
    ) -> None:
        self._provider = provider
        self._model_name = model
        self._system_instruction = system_instruction
        self._history_max_turns = history_max_turns
        self._history: list[dict] = []
        self._thread_id = f"kugane_{uuid.uuid4().hex[:8]}"
        self._checkpointer = InMemorySaver()
        self._cb_lock = threading.RLock()
        self._active_callback: Optional[ProgressCallback] = None

        try:
            self._model: BaseChatModel = chat_model or build_chat_model(
                provider=provider,
                api_key=api_key,
                model=model,
                flask_url=flask_url,
                flask_timeout=flask_timeout,
                flask_api_key=flask_api_key,
            )
        except ProviderConfigError:
            raise
        except Exception as exc:
            raise ProviderConfigError(f"Failed to initialise LLM provider: {exc}") from exc

        set_vision_model_getter(lambda: self._model)
        set_blender_model_getter(lambda: self._model)
        self._build_agents()

    def _emit_progress(self, agent: str, title: str, detail: str = "", status: str = "running") -> None:
        with self._cb_lock:
            cb = self._active_callback
        if cb is not None:
            try:
                cb(AgentProgressEvent(agent=agent, title=title, detail=detail, status=status))
            except Exception:
                log.debug("Progress callback error", exc_info=True)

    def _run_subagent(self, agent_name: str, compiled_agent: Any, task: str) -> str:
        """Stream a specialist sub-agent and emit live progress per tool execution."""
        self._emit_progress(agent_name, f"{agent_name} started", task[:80], "running")
        final_text = ""
        try:
            for chunk in compiled_agent.stream(
                {"messages": [HumanMessage(content=task)]},
                stream_mode="updates",
            ):
                for node_name, update in chunk.items():
                    msgs = update.get("messages", []) if isinstance(update, dict) else []
                    for msg in msgs:
                        if isinstance(msg, AIMessage):
                            if msg.tool_calls:
                                for tc in msg.tool_calls:
                                    tname = tc.get("name", "tool")
                                    self._emit_progress(
                                        agent_name,
                                        _friendly_tool_title(tname),
                                        "",
                                        "running",
                                    )
                            else:
                                txt = _extract_text_from_message(msg)
                                if txt:
                                    final_text = txt
                        elif getattr(msg, "type", "") == "tool":
                            tname = getattr(msg, "name", "") or "tool"
                            self._emit_progress(
                                agent_name,
                                _friendly_tool_title(tname),
                                "Completed",
                                "done",
                            )
            self._emit_progress(agent_name, f"{agent_name} finished", "", "done")
            return final_text or f"{agent_name} completed the task."
        except Exception as exc:
            self._emit_progress(agent_name, f"{agent_name} failed", str(exc)[:100], "error")
            return f"{agent_name} error: {exc}"

    def _build_agents(self) -> None:
        vision_agent = create_agent(
            model=self._model,
            tools=[capture_current_screen, inspect_screen_with_vlm],
            system_prompt=(
                "You are VisionAgent, Kugane's screen-awareness specialist (inspired by Project Astra). "
                "Use capture_current_screen and inspect_screen_with_vlm to observe what is currently "
                "on the user's screen and return precise, factual visual details."
            ),
            name="VisionAgent",
        )

        blender_agent = create_agent(
            model=self._model,
            tools=[
                detect_blender,
                create_blender_model_script,
                run_blender_script,
                verify_blender_model_against_requirements,
                open_blender_model_gui,
                save_blender_model_keep_safe,
                list_stored_blender_models,
            ],
            system_prompt=(
                "You are BlenderAgent, Kugane's precision 3D modeling & verification specialist.\n"
                "Take the time needed to craft genuinely realistic, accurate, multi-part 3D models:\n"
                "1) Call detect_blender first.\n"
                "2) Design detailed sub-assemblies rather than crude single primitives! Use real-world "
                "proportions, bmesh / lathe profiles (kugane_create_lathe_profile), boolean cutouts "
                "(kugane_boolean_cut), solidify shells (kugane_add_solidify), bevels (kugane_add_bevel), "
                "subsurf smoothing (kugane_add_subsurf / kugane_set_smooth), flush snapping "
                "(kugane_place_on_ground / kugane_snap_on_top), and rich PBR materials with micro-bump "
                "(kugane_make_material + kugane_assign_material). NEVER use deprecated mesh.use_auto_smooth "
                "or Principled BSDF 'Specular'.\n"
                "3) Save via create_blender_model_script and build in background via "
                "run_blender_script(script_path=..., open_gui=False). If any Python error occurs, fix and re-run.\n"
                "4) MANDATORY VERIFICATION: Call verify_blender_model_against_requirements(model_name, user_requirements). "
                "If passed=False or accuracy_score < 7, read missing_features / refinement_instructions, improve the "
                "script to make the model more accurate & realistic, rebuild via run_blender_script(..., open_gui=False), "
                "and re-verify (up to 2 refinement cycles).\n"
                "5) ONLY AFTER verification passes (100% built & verified accurate), call open_blender_model_gui(model_name) "
                "to open the completed model in Blender on the user's system.\n"
                "6) Retention policy: Only the last 2 unpinned models remain on disk; older ones auto-delete unless "
                "the user asks to keep/save a model safely (save_blender_model_keep_safe)."
            ),
            name="BlenderAgent",
        )

        engine_agent = create_agent(
            model=self._model,
            tools=[
                detect_game_engines,
                setup_unity_scene_and_mechanics,
                setup_unreal_scene_and_mechanics,
            ],
            system_prompt=(
                "You are GameEngineAgent, Kugane's Unity and Unreal Engine specialist. "
                "1) Call detect_game_engines to discover Unity/Unreal installations. "
                "2) Import 3D models (from BlenderAgent or user) and generate clean gameplay mechanics "
                "scripts via setup_unity_scene_and_mechanics (C# MonoBehaviour + Editor AutoSetup) or "
                "setup_unreal_scene_and_mechanics (Unreal Editor Python import/spawn + physics/mechanics). "
                "Report exact created project/script paths and whether the editor was launched."
            ),
            name="GameEngineAgent",
        )

        orchestrator = self

        @tool
        def delegate_to_vision_agent(task_description: str) -> str:
            """
            Delegate a screen-reading or desktop visual inspection task to VisionAgent.
            Use whenever the user asks about what is currently on their screen or wants
            you to reference an app/viewport/image visible on the monitor.
            """
            return orchestrator._run_subagent("VisionAgent", vision_agent, task_description)

        @tool
        def delegate_to_blender_agent(task_description: str) -> str:
            """
            Delegate a 3D modeling, procedural geometry, material, or FBX/GLB export
            task to BlenderAgent.
            """
            return orchestrator._run_subagent("BlenderAgent", blender_agent, task_description)

        @tool
        def delegate_to_game_engine_agent(task_description: str) -> str:
            """
            Delegate a Unity or Unreal Engine task (importing 3D models, creating C# or
            Unreal Python gameplay mechanics, opening the scene in Unity/Unreal) to
            GameEngineAgent. Pass any exported 3D model path from BlenderAgent!
            """
            return orchestrator._run_subagent("GameEngineAgent", engine_agent, task_description)

        supervisor_prompt = (
            f"{self._system_instruction}\n\n"
            "Delegation Guidelines:\n"
            "- For normal questions, coding help, or analyzing user-uploaded files (PDFs, images, docs), "
            "answer directly without unnecessary tool calls.\n"
            "- When the user asks you to look at their current screen, inspect an open app, or use "
            "live screen context, call delegate_to_vision_agent.\n"
            "- When the user asks to create a 3D model in Blender, or asks to keep/save a generated model safely, "
            "call delegate_to_blender_agent.\n"
            "- When the user asks to open a model in Unity or Unreal and add game mechanics, first "
            "ensure the model exists (via delegate_to_blender_agent if needed), then pass its exported "
            "file path to delegate_to_game_engine_agent.\n"
            "- Combine agents in sequence for end-to-end workflows (e.g. VisionAgent -> BlenderAgent -> GameEngineAgent)."
        )

        self._supervisor = create_agent(
            model=self._model,
            tools=[
                delegate_to_vision_agent,
                delegate_to_blender_agent,
                delegate_to_game_engine_agent,
            ],
            system_prompt=supervisor_prompt,
            checkpointer=self._checkpointer,
            name="Supervisor",
        )

    def send(
        self,
        user_text: str,
        file_paths: list[str] | None = None,
        include_screen: bool = False,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> str:
        """
        Process a user prompt (plus optional uploaded files & live screen capture)
        through the LangChain multi-agent supervisor.
        """
        user_text = user_text.strip()
        files = [f for f in (file_paths or []) if f]
        if not user_text and not files and not include_screen:
            return ""

        self._trim_history()
        with self._cb_lock:
            self._active_callback = progress_callback

        try:
            self._emit_progress("Supervisor", "Planning request", "", "running")

            blocks: list[dict[str, Any]] = []
            if include_screen:
                self._emit_progress("VisionAgent", "Capturing current screen", "", "running")
                screen_info = capture_screen_file("screen_context.png")
                blocks.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{screen_info['base64_jpeg']}"},
                    }
                )
                blocks.append(
                    {
                        "type": "text",
                        "text": f"[Attached Live Screen Snapshot: {screen_info['image_path']}]",
                    }
                )
                self._emit_progress("VisionAgent", "Screen captured", "", "done")

            for fp in files:
                blocks.append(FileProcessor.to_langchain_block(fp))

            prompt_text = user_text or (
                "Please read and analyze the attached file(s)/screen and help me with what is shown."
            )
            if blocks:
                blocks.append({"type": "text", "text": prompt_text})
                human_msg = HumanMessage(content=blocks)
            else:
                human_msg = HumanMessage(content=prompt_text)

            final_reply = ""
            config = {"configurable": {"thread_id": self._thread_id}}
            for chunk in self._supervisor.stream(
                {"messages": [human_msg]},
                config=config,
                stream_mode="updates",
            ):
                for _node_name, update in chunk.items():
                    msgs = update.get("messages", []) if isinstance(update, dict) else []
                    for msg in msgs:
                        if isinstance(msg, AIMessage):
                            if msg.tool_calls:
                                for tc in msg.tool_calls:
                                    tname = tc.get("name", "tool")
                                    self._emit_progress(
                                        "Supervisor",
                                        _friendly_tool_title(tname),
                                        "",
                                        "running",
                                    )
                            else:
                                txt = _extract_text_from_message(msg)
                                if txt:
                                    final_reply = txt

            self._emit_progress("Supervisor", "Completed", "", "done")
            final_reply = final_reply.strip()

            entry: dict = {"role": "user", "text": user_text}
            if files:
                entry["files"] = [Path(fp).name for fp in files]
            self._history.append(entry)
            self._history.append({"role": "assistant", "text": final_reply})
            return final_reply

        except Exception as exc:
            err_msg = str(exc)
            log.error("Orchestrator error: %s", err_msg)
            self._emit_progress("Supervisor", "Error", err_msg[:100], "error")
            raise RuntimeError(f"Kugane agent request failed: {err_msg}") from exc
        finally:
            with self._cb_lock:
                self._active_callback = None

    def clear_history(self) -> None:
        self._history.clear()
        self._thread_id = f"kugane_{uuid.uuid4().hex[:8]}"

    @property
    def history(self) -> list[dict]:
        return list(self._history)

    def _trim_history(self) -> None:
        max_entries = self._history_max_turns * 2
        if len(self._history) > max_entries:
            self._history = self._history[-max_entries:]
