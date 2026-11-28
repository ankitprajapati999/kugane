# -*- coding: utf-8 -*-
"""
ui/compact_view.py — Compact Dynamic Island top notch bar.

Displays Kugane's rounded square logo, brand label, live status dot,
optional active status text (hidden in idle), and animated waveform.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QEnterEvent, QFont
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ui.theme import (
    ACCENT_AMBER, ACCENT_GREEN, ACCENT_PRIMARY, ACCENT_RED, TEXT_PRIMARY,
    TEXT_SECONDARY, make_font,
)
from ui.widgets import KuganeLogoWidget, PulseDotWidget, WaveformWidget


class CompactCapsuleView(QWidget):
    """Compact Dynamic Island notch interior: logo, brand/status, waveform."""

    hover_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CompactCapsule")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 7, 12, 7)
        row.setSpacing(10)

        self._logo = KuganeLogoWidget(size=32, radius=8)
        row.addWidget(self._logo, alignment=Qt.AlignmentFlag.AlignVCenter)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)

        self._label = QLabel("KUGANE")
        self._label.setFont(make_font(10.0, QFont.Weight.Medium))
        self._label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; background: transparent; border: none; letter-spacing: 0.8px;"
        )

        self._dot = PulseDotWidget(ACCENT_GREEN, size=8)

        self._sub_label = QLabel("")
        self._sub_label.setFont(make_font(8.8, QFont.Weight.Normal))
        self._sub_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; background: transparent; border: none;"
        )
        self._sub_label.hide()

        title_row.addWidget(self._label, alignment=Qt.AlignmentFlag.AlignVCenter)
        title_row.addWidget(self._dot, alignment=Qt.AlignmentFlag.AlignVCenter)
        title_row.addWidget(self._sub_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        title_row.addStretch()

        row.addLayout(title_row, stretch=1)

        self._waveform = WaveformWidget(ACCENT_PRIMARY)
        row.addWidget(self._waveform, alignment=Qt.AlignmentFlag.AlignVCenter)

    def set_idle_state(self):
        self._dot.set_color(ACCENT_GREEN, pulse=True)
        self._label.setText("KUGANE")
        self._label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; background: transparent; border: none; letter-spacing: 0.8px;"
        )
        self._sub_label.setText("")
        self._sub_label.hide()
        self._waveform.set_color(ACCENT_PRIMARY)
        self._waveform.set_active(False)

    def set_thinking_state(self, detail: str = "Thinking..."):
        self._dot.set_color(ACCENT_PRIMARY, pulse=True)
        self._label.setText("KUGANE")
        self._label.setStyleSheet(
            f"color: {ACCENT_PRIMARY}; background: transparent; border: none; letter-spacing: 0.8px;"
        )
        self._sub_label.setText(detail or "Thinking...")
        self._sub_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; background: transparent; border: none;"
        )
        self._sub_label.show()
        self._waveform.set_color(ACCENT_PRIMARY)
        self._waveform.set_active(True)

    def set_loading_state(self, message: str = "Loading..."):
        self._dot.set_color(ACCENT_AMBER, pulse=True)
        self._label.setText("KUGANE")
        self._label.setStyleSheet(
            f"color: {ACCENT_AMBER}; background: transparent; border: none; letter-spacing: 0.8px;"
        )
        self._sub_label.setText(message)
        self._sub_label.setStyleSheet(
            f"color: {ACCENT_AMBER}; background: transparent; border: none;"
        )
        self._sub_label.show()
        self._waveform.set_color(ACCENT_AMBER)
        self._waveform.set_active(False)

    def set_error_state(self, message: str = "Error"):
        self._dot.set_color(ACCENT_RED, pulse=False)
        self._label.setText("KUGANE")
        self._label.setStyleSheet(
            f"color: {ACCENT_RED}; background: transparent; border: none; letter-spacing: 0.8px;"
        )
        self._sub_label.setText(message)
        self._sub_label.setStyleSheet(
            f"color: {ACCENT_RED}; background: transparent; border: none;"
        )
        self._sub_label.show()
        self._waveform.set_color(ACCENT_RED)
        self._waveform.set_active(False)

    def enterEvent(self, event: QEnterEvent):
        self.hover_changed.emit(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hover_changed.emit(False)
        super().leaveEvent(event)
