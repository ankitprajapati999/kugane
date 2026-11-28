# -*- coding: utf-8 -*-
"""
config/settings.py — Kugane configuration loader.

Reads environment variables from .env (via python-dotenv) and exposes
typed constants used across the application.  Never logs or prints the
API key.
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # graceful degradation if dotenv not installed
    load_dotenv = None  # type: ignore

# ── Load .env from project root ───────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _ROOT / ".env"

if load_dotenv is not None:
    load_dotenv(_ENV_FILE, override=False)

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT: Path = _ROOT
GENERATED_WORKSPACE: Path = Path(
    os.environ.get("KUGANE_WORKSPACE", str(_ROOT / "workspace"))
)

# ── LLM / VLM Provider Selection ("gemini" or "flask_vlm") ────────────────────
LLM_PROVIDER: str = os.environ.get("LLM_PROVIDER", "gemini").strip().lower() or "gemini"

# ── Gemini ────────────────────────────────────────────────────────────────────
GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "").strip() or "gemini-3.5-flash-lite"

# ── Remote Laptop Local Flask VLM Endpoint ────────────────────────────────────
FLASK_VLM_URL: str = os.environ.get("FLASK_VLM_URL", "http://127.0.0.1:5000/chat").strip()
FLASK_VLM_TIMEOUT: float = float(os.environ.get("FLASK_VLM_TIMEOUT", "120"))
FLASK_VLM_API_KEY: str = os.environ.get("FLASK_VLM_API_KEY", "").strip()

# ── 3D & Game Engine Executables / Default Projects ───────────────────────────
BLENDER_PATH: str = os.environ.get("BLENDER_PATH", "").strip()
UNITY_PATH: str = os.environ.get("UNITY_PATH", "").strip()
UNREAL_PATH: str = os.environ.get("UNREAL_PATH", "").strip()
UNITY_DEFAULT_PROJECT: str = os.environ.get("UNITY_DEFAULT_PROJECT", "").strip()
UNREAL_DEFAULT_PROJECT: str = os.environ.get("UNREAL_DEFAULT_PROJECT", "").strip()

# ── Conversation ──────────────────────────────────────────────────────────────
# Maximum number of exchange pairs kept in in-memory session history
HISTORY_MAX_TURNS: int = int(os.environ.get("HISTORY_MAX_TURNS", "40"))

# ── System instruction for Kugane Multi-Agent Orchestrator ────────────────────
KUGANE_SYSTEM_INSTRUCTION: str = (
    "You are Kugane, an ultra-smart, super friendly AI desktop companion and "
    "Multi-Agent Orchestrator living on the user's Windows PC! ✨\n\n"
    "Tone & Personality:\n"
    "- Be friendly, sharp, expressive, and genuinely helpful with clean modern energy.\n"
    "- Always format responses using clear Markdown: bold highlights, bullet points, "
    "file paths, and code blocks where helpful.\n\n"
    "Uploaded Files & Media Comprehension:\n"
    "- When the user uploads media (PDFs, documents, images, videos, audio, spreadsheets, or code), "
    "read the content carefully and ground your answers directly in what is in those files.\n"
    "- Remember uploaded files across follow-up turns so the user can keep discussing them.\n\n"
    "Phase 2 Multi-Agent Capabilities (Blender, Unity/Unreal, Screen Vision):\n"
    "- You orchestrate specialized agents via LangChain tools:\n"
    "  1. VisionAgent: Can capture and inspect the user's current screen (Astra-style live context).\n"
    "  2. BlenderAgent: Can generate procedural Blender Python (bpy) scripts, build 3D models, "
    "and export .fbx / .glb / .blend assets.\n"
    "  3. GameEngineAgent: Can detect Unity & Unreal Engine, import 3D models into projects, "
    "write C# / Unreal Python game mechanics, and open projects in Unity or Unreal.\n"
    "- Never lie about tool outcomes: report exact generated file paths, engine detection status, "
    "and any missing installation paths honestly."
)
