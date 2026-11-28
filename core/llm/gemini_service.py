# -*- coding: utf-8 -*-
"""
core/llm/gemini_service.py — Gemini conversational service.

Responsibilities:
  - Initialise the google-genai client once.
  - Maintain in-memory chat history for the current session.
  - Send user messages and return assistant responses.
  - Handle API errors with clear, non-crashing messages.

Design contract:
  - Completely independent of PyQt.  No widget imports here.
  - Can be replaced by a local LLM provider by swapping this module.
  - Never logs or surfaces the API key.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from core.media.file_processor import FileProcessor

log = logging.getLogger(__name__)

# ── Lazy import so the module can be imported even if google-genai isn't
# ── installed yet (the caller will get a clear ConfigurationError).
_genai = None


def _get_genai():
    global _genai
    if _genai is None:
        try:
            import google.genai as genai  # type: ignore
            _genai = genai
        except ImportError as exc:
            raise ImportError(
                "google-genai is not installed. Run: uv add google-genai"
            ) from exc
    return _genai


class ConfigurationError(Exception):
    """Raised when the service cannot start due to missing configuration."""


class GeminiService:
    """
    Stateful Gemini chat service for a single application session.

    Usage::

        svc = GeminiService(api_key=GEMINI_API_KEY, model=GEMINI_MODEL)
        response = svc.send("What is the capital of France?")
        print(response)  # "Paris."
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        system_instruction: str = "",
        history_max_turns: int = 40,
    ) -> None:
        if not api_key or api_key.startswith("your_"):
            raise ConfigurationError(
                "GEMINI_API_KEY is missing or still set to the placeholder value.\n"
                "Add your key to the .env file:\n"
                "  GEMINI_API_KEY=your_actual_key_here"
            )

        self._model_name = model
        self._system_instruction = system_instruction
        self._history_max_turns = history_max_turns
        self._history: list[dict] = []   # list of {"role": ..., "parts": [...]}
        self._client = None
        self._chat = None

        self._init_client(api_key)

    # ── Initialisation ─────────────────────────────────────────────────────────

    def _init_client(self, api_key: str) -> None:
        genai = _get_genai()
        try:
            self._client = genai.Client(api_key=api_key)
            # Verify the model name is reachable by creating the chat object
            self._reset_chat()
            log.info("GeminiService ready — model=%s", self._model_name)
        except Exception as exc:
            raise ConfigurationError(
                f"Failed to initialise Gemini client: {exc}\n"
                "Check that your GEMINI_API_KEY is valid."
            ) from exc

    def _reset_chat(self) -> None:
        """Create a fresh Chat object, optionally pre-seeded with history."""
        self._chat = self._client.chats.create(
            model=self._model_name,
            config={
                "system_instruction": self._system_instruction,
            },
        )

    # ── Public API ─────────────────────────────────────────────────────────────

    def send(self, user_text: str, file_paths: list[str] | None = None) -> str:
        """
        Send a user message (and optional attached files), returning the assistant reply.

        Attached files (PDFs, images, audio, video, docs, code) are converted via
        FileProcessor and passed into the active Gemini Chat session so follow-up
        turns continue referencing the uploaded media seamlessly.
        """
        if self._chat is None:
            raise ConfigurationError("GeminiService is not initialised.")

        user_text = user_text.strip()
        files = [f for f in (file_paths or []) if f]
        if not user_text and not files:
            return ""

        self._trim_history()
        genai = _get_genai()

        try:
            if files:
                parts = [
                    FileProcessor.to_gemini_part(fp, genai, self._client)
                    for fp in files
                ]
                prompt = user_text or (
                    "Please read and analyze the attached file(s), then summarize "
                    "the key points and let me know what I can ask next."
                )
                parts.append(prompt)
                response = self._chat.send_message(parts)
            else:
                response = self._chat.send_message(user_text)

            reply = response.text.strip()

            history_entry: dict = {"role": "user", "text": user_text}
            if files:
                history_entry["files"] = [Path(fp).name for fp in files]
            self._history.append(history_entry)
            self._history.append({"role": "assistant", "text": reply})

            return reply

        except Exception as exc:
            err_msg = str(exc)
            log.error("Gemini API error: %s", err_msg)
            raise RuntimeError(
                f"Gemini request failed: {err_msg}"
            ) from exc

    def clear_history(self) -> None:
        """Reset conversation context — starts a fresh chat session."""
        self._history.clear()
        self._reset_chat()

    @property
    def history(self) -> list[dict]:
        """Read-only view of the in-memory conversation history."""
        return list(self._history)

    # ── Internal ───────────────────────────────────────────────────────────────

    def _trim_history(self) -> None:
        """Drop oldest turns if history exceeds the configured limit."""
        max_entries = self._history_max_turns * 2  # each turn = 2 entries
        if len(self._history) > max_entries:
            self._history = self._history[-max_entries:]

