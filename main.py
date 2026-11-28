# -*- coding: utf-8 -*-
"""
main.py — Kugane application entry point.

Composition order:
  1. Load environment / settings (supports Gemini API or remote Flask VLM server).
  2. Initialise LangChain MultiAgentOrchestrator (Vision, Blender, Unity/Unreal).
  3. Build PyQt6 application and Dynamic Island window.
  4. Wire user submit → AgentWorker → live progress + response / error.
  5. Enter Qt event loop.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from config.settings import (
    FLASK_VLM_API_KEY,
    FLASK_VLM_TIMEOUT,
    FLASK_VLM_URL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    HISTORY_MAX_TURNS,
    KUGANE_SYSTEM_INSTRUCTION,
    LLM_PROVIDER,
)
from core.agents.orchestrator import MultiAgentOrchestrator
from core.llm.gemini_worker import AgentWorker
from core.llm.providers import ProviderConfigError
from ui.island_window import DynamicIslandWindow

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("kugane.main")


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Kugane")
    # DynamicIslandWindow uses Qt.WindowType.Tool; keep app alive when dialogs close.
    app.setQuitOnLastWindowClosed(False)
    logo_path = Path(__file__).resolve().parent / "ui" / "Assets" / "Final Logo.png"
    if logo_path.exists():
        app.setWindowIcon(QIcon(str(logo_path)))

    # ── 1. Build UI first so it's visible immediately ─────────────────────────
    window = DynamicIslandWindow()
    window.show()

    # ── 2. Initialise LangChain Multi-Agent Orchestrator ──────────────────────
    orchestrator: MultiAgentOrchestrator | None = None
    try:
        orchestrator = MultiAgentOrchestrator(
            provider=LLM_PROVIDER,
            api_key=GEMINI_API_KEY,
            model=GEMINI_MODEL,
            flask_url=FLASK_VLM_URL,
            flask_timeout=FLASK_VLM_TIMEOUT,
            flask_api_key=FLASK_VLM_API_KEY,
            system_instruction=KUGANE_SYSTEM_INSTRUCTION,
            history_max_turns=HISTORY_MAX_TURNS,
        )
    except ProviderConfigError as exc:
        window.set_state("no_key")
        window.add_error_message(str(exc))
        window._expand()
        log.error("LLM provider config error: %s", exc)
    except Exception as exc:  # noqa: BLE001
        window.set_state("error", detail="Agent init failed")
        window.add_error_message(f"Failed to initialise Kugane orchestrator: {exc}")
        window._expand()
        log.exception("Unexpected error initialising MultiAgentOrchestrator")

    # ── 3. Active AgentWorker instances (kept alive until finished) ───────────
    _active_workers: list[AgentWorker] = []

    def _cleanup_worker(worker: AgentWorker) -> None:
        try:
            _active_workers.remove(worker)
        except ValueError:
            pass

    def on_user_submit(
        text: str,
        file_paths: list[str] | None = None,
        include_screen: bool = False,
    ) -> None:
        if orchestrator is None:
            window.on_llm_error(
                "LLM provider is not configured.\n"
                "Set GEMINI_API_KEY (or LLM_PROVIDER=flask_vlm + FLASK_VLM_URL) in .env and restart Kugane."
            )
            return

        worker = AgentWorker(
            service=orchestrator,
            user_text=text,
            file_paths=file_paths,
            include_screen=include_screen,
        )
        _active_workers.append(worker)

        worker.step_updated.connect(window.on_agent_step)
        worker.status_changed.connect(window.on_agent_status)
        worker.response_ready.connect(window.on_llm_response)
        worker.error_occurred.connect(window.on_llm_error)
        worker.finished.connect(lambda w=worker: _cleanup_worker(w))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    window.user_message_submitted_ex.connect(on_user_submit)

    # ── 4. Event loop ─────────────────────────────────────────────────────────
    exit_code = app.exec()

    # ── 5. Clean shutdown ─────────────────────────────────────────────────────
    for w in list(_active_workers):
        w.quit()
        w.wait(2000)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
