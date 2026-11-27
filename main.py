# -*- coding: utf-8 -*-
"""
main.py — Kugane application entry point.

Composition order:
  1. Load environment / settings.
  2. Initialise GeminiService (or surface a configuration error).
  3. Build PyQt6 application and Dynamic Island window.
  4. Wire user submit → GeminiWorker → window.on_llm_response / on_llm_error.
  5. Enter Qt event loop.
"""
from __future__ import annotations

import sys
import logging

from PyQt6.QtWidgets import QApplication

from config.settings import (
    GEMINI_API_KEY, GEMINI_MODEL, KUGANE_SYSTEM_INSTRUCTION,
    HISTORY_MAX_TURNS,
)
from core.llm.gemini_service import GeminiService, ConfigurationError
from core.llm.gemini_worker import GeminiWorker
from ui.island_window import DynamicIslandWindow

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("kugane.main")


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Kugane")

    # ── 1. Build UI first so it's visible immediately ─────────────────────────
    window = DynamicIslandWindow()
    window.show()

    # ── 2. Initialise Gemini service ──────────────────────────────────────────
    gemini: GeminiService | None = None
    try:
        gemini = GeminiService(
            api_key=GEMINI_API_KEY,
            model=GEMINI_MODEL,
            system_instruction=KUGANE_SYSTEM_INSTRUCTION,
            history_max_turns=HISTORY_MAX_TURNS,
        )
    except ConfigurationError as exc:
        window.set_state("no_key")
        window.add_error_message(str(exc))
        window._expand()          # auto-open so the user sees the error
        log.error("Gemini config error: %s", exc)
        # Don't exit — let the user at least see the error message in the UI
    except Exception as exc:  # noqa: BLE001
        window.set_state("error", detail="Gemini init failed")
        window.add_error_message(f"Failed to initialise Gemini: {exc}")
        window._expand()
        log.exception("Unexpected error initialising Gemini")

    # ── 3. Active GeminiWorker instances (kept alive until finished) ──────────
    _active_workers: list[GeminiWorker] = []

    def _cleanup_worker(worker: GeminiWorker) -> None:
        try:
            _active_workers.remove(worker)
        except ValueError:
            pass

    def on_user_submit(text: str) -> None:
        """
        Called by the UI on user message submission.
        Spawns a GeminiWorker QThread for the API call.
        """
        if gemini is None:
            window.on_llm_error(
                "Gemini is not configured.\n"
                "Add GEMINI_API_KEY to your .env file and restart Kugane."
            )
            return

        worker = GeminiWorker(service=gemini, user_text=text)
        _active_workers.append(worker)

        worker.response_ready.connect(
            lambda reply, w=worker: (window.on_llm_response(reply), _cleanup_worker(w))
        )
        worker.error_occurred.connect(
            lambda msg, w=worker: (window.on_llm_error(msg), _cleanup_worker(w))
        )
        worker.start()

    # Wire UI signal → Gemini pipeline
    window.user_message_submitted.connect(on_user_submit)

    # ── 4. Event loop ─────────────────────────────────────────────────────────
    exit_code = app.exec()

    # ── 5. Clean shutdown ─────────────────────────────────────────────────────
    for w in list(_active_workers):
        w.quit()
        w.wait(2000)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
