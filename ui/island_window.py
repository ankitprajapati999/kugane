# -*- coding: utf-8 -*-
"""
ui/island_window.py — Kugane Dynamic Island Assistant (Pure Text UI & Advanced Animations).

States
------
  State 01 — Idle / Compact     (● KUGANE |||) - Calm floating capsule with pulsing dot
  State 02 — Thinking / Active  (● KUGANE |||) - Active animated waveform and glowing accent
  State 03 — Expanded Assistant - Dual-bubble: compact pill on top + conversation card below
"""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import (
    Qt, QRect, QTimer, QPropertyAnimation, QEasingCurve,
    QPoint, pyqtSignal, QSize, QParallelAnimationGroup, QEvent,
)
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QPainterPath, QPen, QBrush,
    QKeyEvent, QMouseEvent, QEnterEvent, QLinearGradient,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QLineEdit, QScrollArea, QSizePolicy, QPushButton,
    QApplication, QGraphicsOpacityEffect,
)

# ── Load user-tweakable config from YAML ──────────────────────────────────────
from config.ui_config import load_ui_config as _load_ui_config

_CFG = _load_ui_config()
_C = _CFG["colors"]
_D = _CFG["dimensions"]
_P = _CFG["position"]
_F = _CFG["fonts"]

# ══════════════════════════════════════════════════════════════════════════════
# DESIGN SYSTEM TOKENS (Loaded from ui_config.yaml with built-in defaults)
# ══════════════════════════════════════════════════════════════════════════════
BG_SURFACE       = "#11141E"
BG_CAPSULE       = "#252B3A"
BG_CAPSULE_HOVER = "#2A3142"
BG_USER_BUBBLE   = "#293F69"
BG_AI_BUBBLE     = "#202634"
BG_COMPOSER      = "#1F2533"
BORDER_PANEL     = "#252B3A"
BORDER_CAPSULE   = "#30394A"
BORDER_HOVER     = "#44526B"
BORDER_COMPOSER  = "#2A3346"
DIVIDER_LINE     = "#252B3A"

ACCENT_BLUE      = _C.get("accent_blue", "#7892FF")
ACCENT_BLUE_HOV  = _C.get("accent_blue_hover", "#8EA5FF")
ACCENT_GREEN     = _C.get("accent_green", "#58D6A0")
ACCENT_AMBER     = _C.get("accent_amber", "#FFB300")
ACCENT_RED       = _C.get("accent_red", "#FF4444")

TEXT_PRIMARY     = _C.get("text_primary", "#E5E9F2")
TEXT_SECONDARY   = _C.get("text_secondary", "#9BAAC5")
TEXT_MUTED       = _C.get("text_muted", "#6B7B99")

FONT_FAMILY_SANS = _F.get("family", "JetBrainsMono Nerd Font")
FONT_FAMILY_MONO = _F.get("family", "JetBrainsMono Nerd Font")


# ══════════════════════════════════════════════════════════════════════════════
# COMPONENT: PulseDotWidget (Gentle breathing dot indicator)
# ══════════════════════════════════════════════════════════════════════════════
class PulseDotWidget(QWidget):
    """Draws a smooth breathing / pulsing circular status indicator."""

    def __init__(self, color: str = ACCENT_BLUE, parent=None):
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self._color = QColor(color)
        self._alpha = 230
        self._dir = -1
        self._pulsing = True

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    def set_color(self, hex_color: str, pulse: bool = True):
        self._color = QColor(hex_color)
        self._pulsing = pulse
        if not pulse:
            self._alpha = 255
        self.update()

    def _tick(self):
        if not self._pulsing:
            return
        self._alpha += self._dir * 4
        if self._alpha <= 140:
            self._alpha = 140
            self._dir = 1
        elif self._alpha >= 255:
            self._alpha = 255
            self._dir = -1
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Subtle halo glow
        glow_color = QColor(self._color)
        glow_color.setAlpha(int(self._alpha * 0.25))
        p.setBrush(QBrush(glow_color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(1, 1, 10, 10)

        # Core dot
        core_color = QColor(self._color)
        core_color.setAlpha(self._alpha)
        p.setBrush(QBrush(core_color))
        p.drawEllipse(2, 2, 8, 8)


# ══════════════════════════════════════════════════════════════════════════════
# COMPONENT: WaveformWidget (5 animated / static vertical bars)
# ══════════════════════════════════════════════════════════════════════════════
class WaveformWidget(QWidget):
    """Draws the 5 vertical waveform bars seen in State 01 with dynamic animation."""

    def __init__(self, color: str = ACCENT_BLUE, parent=None):
        super().__init__(parent)
        self.setFixedSize(22, 18)
        self._color = QColor(color)
        self._bars = [4, 8, 14, 8, 4]  # Bar heights in pixels
        self._active = False
        self._phase = 0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate_tick)

    def set_color(self, hex_color: str):
        self._color = QColor(hex_color)
        self.update()

    def set_active(self, active: bool):
        self._active = active
        if active:
            if not self._timer.isActive():
                self._timer.start(75)
        else:
            self._timer.stop()
            self._bars = [4, 8, 14, 8, 4]
            self.update()

    def _animate_tick(self):
        self._phase = (self._phase + 1) % 6
        presets = [
            [4, 8, 14, 8, 4],
            [5, 11, 16, 10, 5],
            [6, 14, 12, 13, 6],
            [5, 12, 16, 9, 4],
            [4, 9, 13, 11, 5],
            [3, 7, 10, 7, 3],
        ]
        self._bars = presets[self._phase]
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QBrush(self._color))
        p.setPen(Qt.PenStyle.NoPen)

        x_start = 2
        cy = self.height() / 2.0

        for h in self._bars:
            y = cy - h / 2.0
            p.drawRoundedRect(QRect(int(x_start), int(y), 2, int(h)), 1, 1)
            x_start += 4


# ══════════════════════════════════════════════════════════════════════════════
# COMPONENT: SparkleIconWidget (AI prompt glyph for composer)
# ══════════════════════════════════════════════════════════════════════════════
class SparkleIconWidget(QWidget):
    """Draws a clean, futuristic 4-point AI spark symbol."""

    def __init__(self, color: str = TEXT_SECONDARY, size: int = 16, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._color = QColor(color)

    def set_color(self, hex_color: str):
        self._color = QColor(hex_color)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QBrush(self._color))
        p.setPen(Qt.PenStyle.NoPen)

        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0

        # Draw 4-point star path
        path = QPainterPath()
        path.moveTo(cx, cy - 6)
        path.quadTo(cx, cy, cx + 6, cy)
        path.quadTo(cx, cy, cx, cy + 6)
        path.quadTo(cx, cy, cx - 6, cy)
        path.quadTo(cx, cy, cx, cy - 6)
        p.drawPath(path)


# ══════════════════════════════════════════════════════════════════════════════
# COMPONENT: Kugane Orbit Logo Badge (Header)
# ══════════════════════════════════════════════════════════════════════════════
class KuganeLogoBadge(QWidget):
    """Draws the rounded square logo badge with Kugane's orbital assistant mark."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(34, 34)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, QColor(34, 42, 60))
        grad.setColorAt(1.0, QColor(24, 30, 43))

        p.setBrush(QBrush(grad))
        p.setPen(QPen(QColor(120, 146, 255, 45), 1))
        p.drawRoundedRect(0, 0, self.width(), self.height(), 8, 8)

        # Orbital assistant swirl icon in #7892FF
        pen = QPen(QColor(ACCENT_BLUE), 1.75, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        cx, cy = self.width() / 2.0, self.height() / 2.0

        # Outer orbital arc
        p.drawArc(int(cx - 9), int(cy - 9), 18, 18, 45 * 16, 260 * 16)
        # Inner orbital arc
        p.drawArc(int(cx - 5), int(cy - 5), 10, 10, 220 * 16, 250 * 16)
        # Center core dot
        p.setBrush(QBrush(QColor(ACCENT_BLUE)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(int(cx - 1.5), int(cy - 1.5), 3, 3)


# ══════════════════════════════════════════════════════════════════════════════
# COMPACT VIEW (Capsule for Idle and Active states)
# ══════════════════════════════════════════════════════════════════════════════
class CompactCapsuleView(QFrame):
    """The floating capsule pill with hover glow and dynamic state transitions."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CompactCapsule")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._is_hovered = False

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(16, 0, 16, 0)
        self._layout.setSpacing(10)

        # Left status indicator: Pulsing dot
        self._dot = PulseDotWidget(ACCENT_BLUE)

        # Center text label
        self._label = QLabel("KUGANE")
        self._label.setFont(QFont(FONT_FAMILY_MONO, 10, QFont.Weight.Bold))
        self._label.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none; letter-spacing: 1px;")

        # Right waveform indicator
        self._waveform = WaveformWidget(ACCENT_BLUE)

        self._layout.addWidget(self._dot, alignment=Qt.AlignmentFlag.AlignVCenter)
        self._layout.addWidget(self._label, alignment=Qt.AlignmentFlag.AlignVCenter)
        self._layout.addStretch()
        self._layout.addWidget(self._waveform, alignment=Qt.AlignmentFlag.AlignVCenter)

    def set_idle_state(self):
        """Idle: Pulsing blue dot + KUGANE + Calm blue waveform."""
        self._dot.set_color(ACCENT_BLUE, pulse=True)
        self._label.setText("KUGANE")
        self._label.setFont(QFont(FONT_FAMILY_MONO, 10, QFont.Weight.Bold))
        self._label.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none; letter-spacing: 1px;")
        self._waveform.set_color(ACCENT_BLUE)
        self._waveform.set_active(False)

    def set_thinking_state(self):
        """Thinking: Bright blue dot + Thinking + Active pulsing waveform."""
        self._dot.set_color(ACCENT_BLUE, pulse=True)
        self._label.setText("Thinking")
        self._label.setFont(QFont(FONT_FAMILY_MONO, 10, QFont.Weight.Bold))
        self._label.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")
        self._waveform.set_color(ACCENT_BLUE)
        self._waveform.set_active(True)

    def set_loading_state(self, message: str = "Loading..."):
        self._dot.set_color(ACCENT_AMBER, pulse=True)
        self._label.setText(message)
        self._label.setFont(QFont(FONT_FAMILY_MONO, 9, QFont.Weight.Bold))
        self._label.setStyleSheet(f"color: {ACCENT_AMBER}; background: transparent; border: none;")
        self._waveform.set_color(ACCENT_AMBER)
        self._waveform.set_active(False)

    def set_error_state(self, message: str = "Error"):
        self._dot.set_color(ACCENT_RED, pulse=False)
        self._label.setText(message)
        self._label.setFont(QFont(FONT_FAMILY_MONO, 9, QFont.Weight.Bold))
        self._label.setStyleSheet(f"color: {ACCENT_RED}; background: transparent; border: none;")
        self._waveform.set_color(ACCENT_RED)
        self._waveform.set_active(False)

    def enterEvent(self, event: QEnterEvent):
        self._is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        radius = self.height() / 2.0
        grad = QLinearGradient(0, 0, 0, self.height())
        if self._is_hovered:
            grad.setColorAt(0.0, QColor(48, 59, 86))
            grad.setColorAt(1.0, QColor(31, 39, 60))
            border_pen = QPen(QColor(142, 165, 255, 80), 1.0)
        else:
            grad.setColorAt(0.0, QColor(38, 46, 68))
            grad.setColorAt(1.0, QColor(24, 30, 46))
            border_pen = QPen(QColor(120, 146, 255, 40), 1.0)

        p.setBrush(QBrush(grad))
        p.setPen(border_pen)
        p.drawRoundedRect(0, 0, self.width(), self.height(), radius, radius)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


# ══════════════════════════════════════════════════════════════════════════════
# MESSAGE BUBBLE WIDGETS (Crisp, High-Contrast Text Rendering)
# ══════════════════════════════════════════════════════════════════════════════
class UserMessageItem(QWidget):
    """User message bubble: Right-aligned, rich blue gradient, radius 16px."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 3, 6, 3)
        layout.addStretch()

        bubble = QFrame()
        bubble.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #314E85, stop:1 #243860);
                border-radius: 16px;
                border: 1px solid rgba(120, 146, 255, 0.25);
            }
        """)
        b_layout = QVBoxLayout(bubble)
        b_layout.setContentsMargins(16, 10, 16, 10)

        font = QFont(FONT_FAMILY_MONO, 11, QFont.Weight.Bold)
        label = QLabel(text)
        label.setFont(font)
        label.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        fm = label.fontMetrics()
        lines = text.split('\n')
        max_line_w = max(fm.horizontalAdvance(l) for l in lines) if lines else 0

        max_content_w = 360
        if max_line_w + 10 <= max_content_w:
            label.setWordWrap(False)
            bubble.setFixedWidth(max_line_w + 10 + 32)
        else:
            label.setWordWrap(True)
            bubble.setFixedWidth(max_content_w + 32)

        b_layout.addWidget(label)
        layout.addWidget(bubble)


class AssistantMessageItem(QWidget):
    """Assistant message: Left-aligned, 'KUGANE' header in blue, smooth gradient bubble, markdown support."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 6, 4)
        layout.setSpacing(6)

        header = QLabel("KUGANE")
        header.setFont(QFont(FONT_FAMILY_MONO, 9, QFont.Weight.Bold))
        header.setStyleSheet(f"color: {ACCENT_BLUE}; background: transparent; border: none; letter-spacing: 0.5px;")
        layout.addWidget(header)

        bubble = QFrame()
        bubble.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1C2333, stop:1 #151A26);
                border-radius: 16px;
                border: 1px solid rgba(120, 146, 255, 0.15);
            }
        """)
        b_layout = QVBoxLayout(bubble)
        b_layout.setContentsMargins(16, 12, 16, 12)

        font = QFont(FONT_FAMILY_MONO, 10, QFont.Weight.Bold)
        label = QLabel()
        label.setFont(font)
        label.setTextFormat(Qt.TextFormat.MarkdownText)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse)
        label.setOpenExternalLinks(True)
        label.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")
        label.setText(text)

        fm = label.fontMetrics()
        lines = text.split('\n')
        max_line_w = max(fm.horizontalAdvance(l) for l in lines) if lines else 0

        max_content_w = 380
        if '\n' in text or len(text) > 80:
            bubble.setFixedWidth(max_content_w + 32)
        elif max_line_w + 10 <= max_content_w:
            bubble.setFixedWidth(max(max_line_w + 10 + 32, 160))
        else:
            bubble.setFixedWidth(max_content_w + 32)

        b_layout.addWidget(label)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(bubble)
        row.addStretch()

        layout.addLayout(row)


# ══════════════════════════════════════════════════════════════════════════════
# CONVERSATION CARD (Separate lower bubble — messages, thinking, composer)
# ══════════════════════════════════════════════════════════════════════════════
class ConversationCardView(QFrame):
    """The conversation card panel that sits below the compact pill with a visual gap."""

    close_requested = pyqtSignal()
    minimize_requested = pyqtSignal()
    message_sent = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ConversationCard")

        main_vbox = QVBoxLayout(self)
        main_vbox.setContentsMargins(20, 14, 20, 16)
        main_vbox.setSpacing(10)

        # ── Thin top bar: logo, Kugane title, minimize, close ─────────────────
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(10)

        self._logo_badge = KuganeLogoBadge()
        title_lbl = QLabel("Kugane")
        title_lbl.setFont(QFont(FONT_FAMILY_SANS, 12, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")

        btn_box = QHBoxLayout()
        btn_box.setSpacing(6)

        min_btn = QPushButton("—")
        min_btn.setFixedSize(26, 26)
        min_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        min_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_SECONDARY};
                border: none;
                font-size: 10pt;
                border-radius: 13px;
            }}
            QPushButton:hover {{
                background: {BG_AI_BUBBLE};
                color: {TEXT_PRIMARY};
            }}
        """)
        min_btn.clicked.connect(self.minimize_requested.emit)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(26, 26)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_SECONDARY};
                border: none;
                font-size: 9pt;
                border-radius: 13px;
            }}
            QPushButton:hover {{
                background: #2D1A22;
                color: {ACCENT_RED};
            }}
        """)
        close_btn.clicked.connect(self.close_requested.emit)

        btn_box.addWidget(min_btn)
        btn_box.addWidget(close_btn)

        header_row.addWidget(self._logo_badge, alignment=Qt.AlignmentFlag.AlignVCenter)
        header_row.addWidget(title_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)
        header_row.addStretch()
        header_row.addLayout(btn_box)
        main_vbox.addLayout(header_row)

        # Divider line (smooth gradient)
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFixedHeight(1)
        divider.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 transparent, stop:0.2 rgba(120, 146, 255, 0.18), stop:0.8 rgba(120, 146, 255, 0.18), stop:1 transparent); border: none;")
        main_vbox.addWidget(divider)

        # ── 2. Conversation Area (Scrollable) ─────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 4px;
                margin: 0px;
                border-radius: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(120, 146, 255, 0.25);
                min-height: 24px;
                border-radius: 2px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)

        self._msg_container = QWidget()
        self._msg_container.setStyleSheet("background: transparent;")
        self._msg_vbox = QVBoxLayout(self._msg_container)
        self._msg_vbox.setContentsMargins(0, 4, 0, 4)
        self._msg_vbox.setSpacing(14)
        self._msg_vbox.addStretch(1)  # Keeps messages pushed to the top

        self._scroll.setWidget(self._msg_container)
        main_vbox.addWidget(self._scroll, stretch=1)

        # Connect scrollbar value change to toggle scroll down button
        self._scroll.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)

        # ── Scroll Down Indicator Pill (as seen in reference) ─────────────────
        scroll_btn_row = QHBoxLayout()
        scroll_btn_row.setContentsMargins(0, 0, 0, 0)

        self._scroll_down_btn = QPushButton("↓")
        self._scroll_down_btn.setFixedSize(28, 28)
        self._scroll_down_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._scroll_down_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1E2536, stop:1 #161C28);
                color: #9BAAC5;
                border: 1px solid rgba(120, 146, 255, 0.18);
                border-radius: 14px;
                font-size: 11pt;
                padding-bottom: 2px;
            }
            QPushButton:hover {
                background: #252E42;
                color: #E5E9F2;
                border: 1px solid rgba(120, 146, 255, 0.35);
            }
        """)
        self._scroll_down_btn.clicked.connect(self._scroll_to_bottom)

        scroll_btn_row.addStretch()
        scroll_btn_row.addWidget(self._scroll_down_btn)
        scroll_btn_row.addStretch()
        main_vbox.addLayout(scroll_btn_row)

        # ── 3. Thinking Status Bubble (Static label + Animated Wave) ─────────
        self._thinking_item = QWidget()
        t_layout = QVBoxLayout(self._thinking_item)
        t_layout.setContentsMargins(0, 0, 0, 0)
        t_layout.setSpacing(4)

        t_header = QLabel("KUGANE")
        t_header.setFont(QFont(FONT_FAMILY_MONO, 9, QFont.Weight.Bold))
        t_header.setStyleSheet(f"color: {ACCENT_BLUE}; letter-spacing: 0.5px; background: transparent; border: none;")

        t_bubble = QFrame()
        t_bubble.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1C2333, stop:1 #151A26);
                border-radius: 14px;
                border: 1px solid rgba(120, 146, 255, 0.18);
            }
        """)
        tb_layout = QHBoxLayout(t_bubble)
        tb_layout.setContentsMargins(16, 10, 16, 10)
        tb_layout.setSpacing(10)

        self._thinking_lbl = QLabel("Thinking")
        self._thinking_lbl.setFont(QFont(FONT_FAMILY_MONO, 11, QFont.Weight.Bold))
        self._thinking_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")

        self._thinking_wave = WaveformWidget(ACCENT_BLUE)
        self._thinking_wave.set_active(True)

        tb_layout.addWidget(self._thinking_lbl)
        tb_layout.addWidget(self._thinking_wave)

        t_row = QHBoxLayout()
        t_row.addWidget(t_bubble)
        t_row.addStretch()

        t_layout.addWidget(t_header)
        t_layout.addLayout(t_row)
        self._thinking_item.hide()
        main_vbox.addWidget(self._thinking_item)

        # ── 4. Bottom Message Composer (Pure Text, Animated Send) ─────────────
        self._composer_frame = QFrame()
        self._composer_frame.setFixedHeight(52)
        self._composer_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1E2536, stop:1 #151B27);
                border: 1px solid rgba(120, 146, 255, 0.22);
                border-radius: 26px;
            }
        """)
        c_layout = QHBoxLayout(self._composer_frame)
        c_layout.setContentsMargins(14, 6, 8, 6)
        c_layout.setSpacing(8)

        # Left prompt sparkle glyph
        self._sparkle_icon = SparkleIconWidget(TEXT_SECONDARY, size=16)

        # Center input field
        self._input_field = QLineEdit()
        self._input_field.setPlaceholderText("Ask Kugane anything...")
        self._input_field.setFont(QFont(FONT_FAMILY_MONO, 10, QFont.Weight.Bold))
        self._input_field.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {TEXT_PRIMARY};
                selection-background-color: {BG_USER_BUBBLE};
            }}
        """)
        self._input_field.returnPressed.connect(self._on_submit)
        self._input_field.textChanged.connect(self._on_text_changed)

        # Right send button: circular periwinkle blue with upward arrow
        self._send_btn = QPushButton("↑")
        self._send_btn.setFixedSize(36, 36)
        self._send_btn.setFont(QFont(FONT_FAMILY_MONO, 13, QFont.Weight.Bold))
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.clicked.connect(self._on_submit)
        self._update_send_button(active=False)

        c_layout.addWidget(self._sparkle_icon)
        c_layout.addWidget(self._input_field, stretch=1)
        c_layout.addWidget(self._send_btn)

        main_vbox.addWidget(self._composer_frame)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Generous rounded rectangle for expanded panel with smooth gradient
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, QColor(20, 23, 38))
        grad.setColorAt(1.0, QColor(13, 16, 25))

        p.setBrush(QBrush(grad))
        p.setPen(QPen(QColor(120, 146, 255, 38), 1.0))
        p.drawRoundedRect(0, 0, self.width(), self.height(), 24, 24)

    def _on_text_changed(self, text: str):
        is_active = bool(text.strip())
        self._update_send_button(active=is_active)
        self._sparkle_icon.set_color(ACCENT_BLUE if is_active else TEXT_SECONDARY)

    def _update_send_button(self, active: bool):
        if active:
            self._send_btn.setEnabled(True)
            self._send_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #8EA5FF, stop:1 #6784FF);
                    color: #FFFFFF;
                    border: none;
                    border-radius: 18px;
                    padding-bottom: 2px;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #A1B4FF, stop:1 #7892FF);
                }
            """)
        else:
            self._send_btn.setEnabled(False)
            self._send_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #232B3B;
                    color: {TEXT_MUTED};
                    border: none;
                    border-radius: 18px;
                    padding-bottom: 2px;
                }}
            """)

    def _on_submit(self):
        text = self._input_field.text().strip()
        if text:
            self._input_field.clear()
            self._update_send_button(active=False)
            self.message_sent.emit(text)

    def add_user_message(self, text: str):
        item = UserMessageItem(text)
        self._msg_vbox.insertWidget(self._msg_vbox.count() - 1, item)
        self._scroll_to_bottom()

    def add_assistant_message(self, text: str):
        item = AssistantMessageItem(text)
        self._msg_vbox.insertWidget(self._msg_vbox.count() - 1, item)
        self._scroll_to_bottom()

    def add_error_message(self, text: str):
        item = AssistantMessageItem(f"⚠ {text}")
        self._msg_vbox.insertWidget(self._msg_vbox.count() - 1, item)
        self._scroll_to_bottom()

    def set_thinking(self, thinking: bool):
        self._thinking_item.setVisible(thinking)
        self._input_field.setEnabled(not thinking)
        self._send_btn.setEnabled(not thinking and bool(self._input_field.text().strip()))
        if thinking:
            self._thinking_wave.set_active(True)
            self._scroll_to_bottom()
        else:
            self._thinking_wave.set_active(False)

    def _on_scroll_changed(self, val: int):
        # Auto-hide scroll button when already near the bottom
        max_val = self._scroll.verticalScrollBar().maximum()
        self._scroll_down_btn.setVisible(max_val > 50 and (max_val - val) > 30)

    def _scroll_to_bottom(self):
        QTimer.singleShot(60, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))


# ══════════════════════════════════════════════════════════════════════════════
# MAIN DYNAMIC ISLAND WINDOW (Dual-Bubble: Compact Pill + Conversation Card)
# ══════════════════════════════════════════════════════════════════════════════
class DynamicIslandWindow(QWidget):
    """
    Kugane Floating Window — Dual-Bubble Architecture:
    - Compact pill capsule centered on top (narrower width).
    - Conversation card drops below the pill with a visual gap.
    - Smooth expand/collapse animation with physics easing.
    - Configurable via config/ui_config.yaml for position, size, colors.
    """

    user_message_submitted: pyqtSignal = pyqtSignal(str)

    # Dimensional anchors — loaded from YAML config
    W_COMPACT  = _D.get("compact_width", 224)
    H_COMPACT  = _D.get("compact_height", 40)
    W_EXPANDED = _D.get("expanded_width", 480)
    H_EXPANDED = _D.get("expanded_height", 520)
    PILL_GAP   = _D.get("pill_gap", 7)

    def __init__(self, on_user_submit_callback: Optional[Callable[[str], None]] = None):
        super().__init__()
        self._submit_cb = on_user_submit_callback
        self._is_expanded = False
        self._current_state = "idle"
        self._pending_request = False
        self._drag_pos: Optional[QPoint] = None

        self._init_window()
        self._build_views()
        self._setup_animation()

        # Start in compact idle
        self.set_state("idle")

    def _init_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        screen = self.screen().geometry()
        # Resolve alignment from YAML config
        align = _P.get("align_x", "center")
        offset = _P.get("offset_x", 0)
        if align == "left":
            self._cx = self.W_COMPACT // 2 + 20 + offset
        elif align == "right":
            self._cx = screen.width() - self.W_COMPACT // 2 - 20 + offset
        else:
            self._cx = screen.width() // 2 + offset

        self._top_y = _P.get("top_y", 48)

        # Position initially at compact geometry
        self.setGeometry(
            self._cx - self.W_COMPACT // 2,
            self._top_y,
            self.W_COMPACT,
            self.H_COMPACT,
        )

    def _build_views(self):
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(self.PILL_GAP)

        # ── 1. Top pill row (narrower, centered within wider window) ──────────
        pill_row = QHBoxLayout()
        pill_row.setContentsMargins(0, 0, 0, 0)
        pill_row.addStretch()

        self._compact_view = CompactCapsuleView()
        self._compact_view.setFixedSize(self.W_COMPACT, self.H_COMPACT)
        self._compact_view.clicked.connect(self._expand)

        pill_row.addWidget(self._compact_view)
        pill_row.addStretch()
        self._layout.addLayout(pill_row)

        # ── 2. Conversation card (wider, appears below the pill) ──────────────
        self._conversation_card = ConversationCardView(self)
        self._conversation_card.close_requested.connect(self._quit_app)
        self._conversation_card.minimize_requested.connect(self._collapse)
        self._conversation_card.message_sent.connect(self._submit)
        self._conversation_card.hide()

        self._layout.addWidget(self._conversation_card, stretch=1)

        # Alias for backward compatibility with external callers
        self._expanded_view = self._conversation_card

    def _quit_app(self):
        """Shut down the Kugane desktop assistant completely."""
        QApplication.instance().quit()

    def changeEvent(self, event: QEvent):
        """Auto-collapse when the user clicks away or focus leaves the widget."""
        if event.type() == QEvent.Type.ActivationChange:
            if not self.isActiveWindow() and self._is_expanded and not (self._anim.state() == QPropertyAnimation.State.Running):
                self._collapse()
        super().changeEvent(event)

    def _setup_animation(self):
        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.finished.connect(self._on_anim_finished)

    def _compact_rect(self) -> QRect:
        return QRect(
            self._cx - self.W_COMPACT // 2,
            self._top_y,
            self.W_COMPACT,
            self.H_COMPACT,
        )

    def _expanded_rect(self) -> QRect:
        return QRect(
            self._cx - self.W_EXPANDED // 2,
            self._top_y,
            self.W_EXPANDED,
            self.H_EXPANDED,
        )

    # ── State Machine ─────────────────────────────────────────────────────────

    def set_state(self, state: str, detail: str = ""):
        """
        Supported states:
          'idle'      -> Calm pill (● KUGANE |||)
          'thinking'  -> Active animated pill / panel thinking bubble
          'loading'   -> Amber pill (● Loading... |||)
          'error'     -> Red pill / error bubble
        """
        self._current_state = state

        if state == "idle":
            self._compact_view.set_idle_state()
            self._expanded_view.set_thinking(False)
        elif state == "thinking":
            self._compact_view.set_thinking_state()
            self._expanded_view.set_thinking(True)
        elif state == "loading":
            self._compact_view.set_loading_state(detail or "Loading...")
            self._expanded_view.set_thinking(False)
        elif state in ("error", "no_key"):
            self._compact_view.set_error_state(detail or "Error")
            self._expanded_view.set_thinking(False)

    def update_status(self, message: str):
        """Safe status update slot."""
        low = message.lower()
        if "loading" in low or "model" in low:
            self.set_state("loading", detail=message)
        elif "error" in low or "failed" in low:
            self.set_state("error", detail="Error")
        else:
            self.set_state("idle")

    # ── Expand / Collapse ─────────────────────────────────────────────────────

    def _expand(self):
        if self._is_expanded or self._anim.state() == QPropertyAnimation.State.Running:
            return
        self._is_expanded = True

        # Switch visibility
        self._compact_view.hide()
        self._expanded_view.show()

        # Animate geometry outward symmetrically from top center
        self._anim.stop()
        self._anim.setStartValue(self.geometry())
        self._anim.setEndValue(self._expanded_rect())
        self._anim.start()

        self.activateWindow()
        self._expanded_view._input_field.setFocus()

    def _collapse(self):
        if not self._is_expanded or self._anim.state() == QPropertyAnimation.State.Running:
            return
        self._is_expanded = False

        # Switch to compact view immediately so expanded view doesn't clamp collapse
        self._expanded_view.hide()
        self._compact_view.show()

        # Animate geometry inward symmetrically toward top center
        self._anim.stop()
        self._anim.setStartValue(self.geometry())
        self._anim.setEndValue(self._compact_rect())
        self._anim.start()

    def _on_anim_finished(self):
        if not self._is_expanded:
            self.setGeometry(self._compact_rect())

    # ── Conversation Pipeline ─────────────────────────────────────────────────

    def _submit(self, text: str):
        if not text.strip() or self._pending_request:
            return
        self._pending_request = True

        # Show user message in expanded view
        if not self._is_expanded:
            self._expand()
        self._expanded_view.add_user_message(text)
        self.set_state("thinking")

        if self._submit_cb:
            self._submit_cb(text)
        self.user_message_submitted.emit(text)

    def on_llm_response(self, reply: str):
        self._pending_request = False
        self._expanded_view.add_assistant_message(reply)
        self.set_state("idle")

    def on_llm_error(self, error_msg: str):
        self._pending_request = False
        self._expanded_view.add_error_message(error_msg)
        self.set_state("error", detail="Error")

    def display_transcription(self, text: str):
        """Safe compatibility slot for any text input."""
        if not self._pending_request and text.strip():
            self._submit(text)

    def add_user_message(self, text: str):
        self._expanded_view.add_user_message(text)

    def add_assistant_message(self, text: str):
        self._expanded_view.add_assistant_message(text)
        self.set_state("idle")

    def add_error_message(self, text: str):
        self._expanded_view.add_error_message(text)
        self.set_state("error", detail="Error")

    # ── Draggable Window Behavior ─────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            self.move(new_pos)
            self._cx = self.geometry().center().x()
            self._top_y = self.geometry().top()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape and self._is_expanded:
            self._collapse()
        else:
            super().keyPressEvent(event)
