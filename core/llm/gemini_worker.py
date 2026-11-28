# -*- coding: utf-8 -*-
"""
core/llm/gemini_worker.py — QThread wrapper for MultiAgentOrchestrator / GeminiService.

Runs blocking LangChain / Gemini / Flask VLM orchestration in a background thread
so the PyQt UI stays responsive, and streams live agent step updates back to the UI.
"""
from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal

from core.agents.orchestrator import AgentProgressEvent
from core.llm.gemini_service import ConfigurationError
from core.llm.providers import ProviderConfigError


class GeminiWorker(QThread):
    """
    Background worker running one orchestrator turn and streaming progress updates.

    Signals
    -------
    step_updated(str, str, str, str) — (agent, title, detail, status)
    status_changed(str)              — Compact notch status label
    response_ready(str)              — Assistant reply text
    error_occurred(str)              — Human-readable error message
    """

    step_updated = pyqtSignal(str, str, str, str)
    status_changed = pyqtSignal(str)
    response_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        service: Any,
        user_text: str,
        file_paths: list[str] | None = None,
        include_screen: bool = False,
    ) -> None:
        super().__init__()
        self._service = service
        self._user_text = user_text
        self._file_paths = list(file_paths or [])
        self._include_screen = include_screen

    def _on_progress(self, ev: AgentProgressEvent) -> None:
        self.step_updated.emit(ev.agent, ev.title, ev.detail, ev.status)
        if ev.status == "running":
            self.status_changed.emit(ev.agent if ev.agent != "Supervisor" else ev.title)

    def run(self) -> None:
        try:
            if hasattr(self._service, "_supervisor"):
                reply = self._service.send(
                    self._user_text,
                    file_paths=self._file_paths,
                    include_screen=self._include_screen,
                    progress_callback=self._on_progress,
                )
            else:
                reply = self._service.send(self._user_text, file_paths=self._file_paths)
            self.response_ready.emit(reply)
        except (ConfigurationError, ProviderConfigError) as exc:
            self.error_occurred.emit(f"Configuration error: {exc}")
        except RuntimeError as exc:
            self.error_occurred.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.error_occurred.emit(f"Unexpected error: {exc}")


AgentWorker = GeminiWorker
