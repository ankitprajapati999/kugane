# -*- coding: utf-8 -*-
"""
ui/messages.py — Chat message bubble widgets for Kugane.

Components:
  - UserMessageItem      : Right-aligned dark bubble with file attachment tags
  - AssistantMessageItem : Left-aligned pitch-black bubble with Markdown rendering
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core.media.file_processor import FileProcessor
from ui.theme import (
    ACCENT_GREEN, ACCENT_PRIMARY, ACCENT_RED, AI_BUBBLE_BORDER, AI_BUBBLE_END,
    AI_BUBBLE_START, TEXT_PRIMARY, TEXT_SECONDARY, USER_BUBBLE_BORDER,
    USER_BUBBLE_END, USER_BUBBLE_START, make_font,
)


class UserMessageItem(QWidget):
    """User message bubble: Right-aligned dark graphite bubble with optional file chips."""

    def __init__(
        self,
        text: str,
        file_paths: list[str] | None = None,
        max_content_w: int = 340,
        parent=None,
    ):
        super().__init__(parent)
        self._text = text
        self._summary = ""

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 3, 6, 3)
        layout.addStretch()

        self._bubble = QFrame()
        self._bubble.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {USER_BUBBLE_START}, stop:1 {USER_BUBBLE_END});
                border-radius: 16px;
                border: 1px solid {USER_BUBBLE_BORDER};
            }}
        """)
        b_layout = QVBoxLayout(self._bubble)
        b_layout.setContentsMargins(16, 10, 16, 10)
        b_layout.setSpacing(6)

        self._files_lbl: QLabel | None = None
        files = [f for f in (file_paths or []) if f]
        if files:
            tags = []
            for fp in files:
                meta = FileProcessor.describe(fp)
                tags.append(f"[{meta.badge}] {meta.name}")
            self._summary = "  •  ".join(tags)
            self._files_lbl = QLabel(self._summary)
            self._files_lbl.setFont(make_font(8.5, QFont.Weight.Medium))
            self._files_lbl.setWordWrap(True)
            self._files_lbl.setMinimumHeight(26)
            self._files_lbl.setStyleSheet(
                f"color: {ACCENT_PRIMARY}; background: rgba(255, 212, 0, 0.08); "
                f"border: 1px solid rgba(255, 212, 0, 0.22); border-radius: 8px; padding: 5px 10px;"
            )
            b_layout.addWidget(self._files_lbl)

        self._label: QLabel | None = None
        if text:
            self._label = QLabel(text)
            self._label.setFont(make_font(10.0, QFont.Weight.Normal))
            self._label.setStyleSheet(
                f"color: {TEXT_PRIMARY}; background: transparent; border: none;"
            )
            self._label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            b_layout.addWidget(self._label)

        self.set_max_bubble_width(max_content_w)
        layout.addWidget(self._bubble)

    def set_max_bubble_width(self, max_content_w: int) -> None:
        max_line_w = 0
        if self._files_lbl is not None:
            max_line_w = max(
                max_line_w,
                self._files_lbl.fontMetrics().horizontalAdvance(self._summary) + 24,
            )
        if self._label is not None:
            fm = self._label.fontMetrics()
            lines = self._text.split("\n")
            text_w = max(fm.horizontalAdvance(l) for l in lines) if lines else 0
            max_line_w = max(max_line_w, text_w)
            self._label.setWordWrap(max_line_w + 12 > max_content_w)

        if max_line_w + 12 <= max_content_w:
            self._bubble.setFixedWidth(max(120, max_line_w + 12 + 32))
        else:
            self._bubble.setFixedWidth(max_content_w + 32)


class AssistantMessageItem(QWidget):
    """Assistant message: Left-aligned, gold 'KUGANE' label, optional agent trace, pitch-black bubble."""

    def __init__(
        self,
        text: str,
        max_content_w: int = 360,
        agent_steps: list[tuple[str, str, str]] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._text = text

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 6, 4)
        layout.setSpacing(6)

        header = QLabel("KUGANE")
        header.setFont(make_font(8.8, QFont.Weight.Medium))
        header.setStyleSheet(
            f"color: {ACCENT_PRIMARY}; background: transparent; border: none; letter-spacing: 0.6px;"
        )
        layout.addWidget(header)

        self._bubble = QFrame()
        self._bubble.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {AI_BUBBLE_START}, stop:1 {AI_BUBBLE_END});
                border-radius: 16px;
                border: 1px solid {AI_BUBBLE_BORDER};
            }}
        """)
        b_layout = QVBoxLayout(self._bubble)
        b_layout.setContentsMargins(16, 12, 16, 12)
        b_layout.setSpacing(8)

        steps = [s for s in (agent_steps or []) if s]
        if steps:
            trace_box = QFrame()
            trace_box.setStyleSheet(
                "QFrame { background: rgba(255, 255, 255, 0.03); "
                "border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; }"
            )
            t_vbox = QVBoxLayout(trace_box)
            t_vbox.setContentsMargins(10, 6, 10, 6)
            t_vbox.setSpacing(3)
            for agent, title, status in steps:
                icon = "✓" if status == "done" else ("✕" if status == "error" else "•")
                color = ACCENT_GREEN if status == "done" else (ACCENT_RED if status == "error" else TEXT_SECONDARY)
                step_lbl = QLabel(f"{icon} {agent} — {title}")
                step_lbl.setFont(make_font(8.2, QFont.Weight.Normal))
                step_lbl.setWordWrap(True)
                step_lbl.setStyleSheet(f"color: {color}; background: transparent; border: none;")
                t_vbox.addWidget(step_lbl)
            b_layout.addWidget(trace_box)

        self._label = QLabel()
        self._label.setFont(make_font(10.0, QFont.Weight.Normal))
        self._label.setTextFormat(Qt.TextFormat.MarkdownText)
        self._label.setWordWrap(True)
        self._label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self._label.setOpenExternalLinks(True)
        self._label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; background: transparent; border: none;"
        )
        self._label.setText(text)
        b_layout.addWidget(self._label)

        self.set_max_bubble_width(max_content_w)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self._bubble)
        row.addStretch()

        layout.addLayout(row)

    def set_max_bubble_width(self, max_content_w: int) -> None:
        fm = self._label.fontMetrics()
        lines = self._text.split("\n")
        max_line_w = max(fm.horizontalAdvance(l) for l in lines) if lines else 0

        if "\n" in self._text or len(self._text) > 80:
            self._bubble.setFixedWidth(max_content_w + 32)
        elif max_line_w + 12 <= max_content_w:
            self._bubble.setFixedWidth(max(max_line_w + 12 + 32, 160))
        else:
            self._bubble.setFixedWidth(max_content_w + 32)
