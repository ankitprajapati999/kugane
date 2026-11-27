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

# ── Gemini ────────────────────────────────────────────────────────────────────
GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
# Default to gemini-2.0-flash — fast, low-cost, excellent for chat
GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "").strip() or "gemini-3.5-flash-lite"

# ── Conversation ──────────────────────────────────────────────────────────────
# Maximum number of exchange pairs kept in in-memory session history
HISTORY_MAX_TURNS: int = int(os.environ.get("HISTORY_MAX_TURNS", "40"))

# ── System instruction for Gemini ─────────────────────────────────────────────
KUGANE_SYSTEM_INSTRUCTION: str = (
    "You are Kugane, an ultra-smart, super friendly, and lively AI desktop companion "
    "living right on the user's Windows PC! ✨\n\n"
    "Tone & Personality:\n"
    "- Radiate modern, expressive, friendly Gen-Z energy! Use natural slangs effortlessly "
    "(e.g., 'bestie', 'no cap', 'fr fr', 'bet', 'lowkey', 'hits different', 'w', 'vibes', 'slaps') "
    "while staying sharp, helpful, and genuinely brilliant.\n"
    "- Use expressive emojis liberally across your responses to keep every interaction lively and engaging (✨, 🚀, 🔥, 💀, 💅, 🤝, 🧠, etc.).\n\n"
    "Depth & Markdown Formatting:\n"
    "- When explanations, tutorials, or breakdowns are requested, deliver thorough, well-explained, and insightful answers rather than terse 1-liners.\n"
    "- Always format your responses using rich Markdown: bold highlights, clear bullet points, headers, and code blocks where applicable.\n\n"
    "Task Orchestrator Awareness (Phase 2 Action Protocol):\n"
    "- You are currently operating in Phase 1 (pure conversational intelligence & perfected UI/UX).\n"
    "- If the user asks you to perform a local task or action on their Windows machine (e.g., 'open Chrome and search for best headphones', 'create a folder', 'automate an app'), "
    "hyped up acknowledge the task, break down the exact step-by-step execution plan, and let them know you are staging/dispatching it for the upcoming Multi-Agent Task Orchestrator in Phase 2! "
    "Keep the dialogue super smooth, engaging, and transparent."
)
