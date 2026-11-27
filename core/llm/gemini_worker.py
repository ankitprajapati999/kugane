# -*- coding: utf-8 -*-
"""
core/llm/gemini_worker.py — QThread wrapper for GeminiService.

Runs the blocking Gemini HTTP call in a background thread so the PyQt
UI thread stays responsive.  Communicates back via Qt signals.
"""
from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from core.llm.gemini_service import GeminiService, ConfigurationError


class GeminiWorker(QThread):
    """
    Background worker that sends one message to Gemini and emits the reply.

    Signals
    -------
    response_ready(str)   — Emitted with the assistant reply text.
    error_occurred(str)   — Emitted with a human-readable error description.
    """

    response_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, service: GeminiService, user_text: str) -> None:
        super().__init__()
        self._service = service
        self._user_text = user_text

    def run(self) -> None:
        try:
            reply = self._service.send(self._user_text)
            self.response_ready.emit(reply)
        except ConfigurationError as exc:
            self.error_occurred.emit(f"Configuration error: {exc}")
        except RuntimeError as exc:
            self.error_occurred.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.error_occurred.emit(f"Unexpected error: {exc}")

