# -*- coding: utf-8 -*-
"""
ui/island_window.py — Kugane Dynamic Island Window Shell.

Coordinates:
  - Top-bezel notch silhouette, physical-inch sizing, and expand/collapse physics
  - Subtle grayish hover backlight on BOTH compact and expanded windows
  - Edge/corner resizing and fullscreen toggle on the expanded pill
  - Top-edge horizontal dragging, Esc/arrow key handling, and focus-loss collapse
"""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import (
    QEasingCurve, QEvent, QPoint, QPropertyAnimation, QRect, QRectF, Qt,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QEnterEvent, QIcon, QKeyEvent, QMouseEvent, QPainter, QPen,
)
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget

from ui.compact_view import CompactCapsuleView
from ui.conversation_card import ConversationCardView
from ui.messages import AssistantMessageItem, UserMessageItem
from ui.theme import (
    DIMENSIONS, LOGO_PATH, NOTCH_BG, NOTCH_BORDER, NOTCH_BORDER_HOVER,
    POSITION, build_notch_paths, parse_color,
)
from ui.widgets import (
    AttachFileButton, KuganeLogoWidget, PulseDotWidget, ScreenVisionButton,
    WaveformWidget,
)

__all__ = [
    "DynamicIslandWindow",
    "CompactCapsuleView",
    "ConversationCardView",
    "UserMessageItem",
    "AssistantMessageItem",
    "KuganeLogoWidget",
    "PulseDotWidget",
    "WaveformWidget",
    "AttachFileButton",
    "ScreenVisionButton",
]


class DynamicIslandWindow(QWidget):
    """
    Kugane Floating Notch Window:
    - Stuck to the top edge of the screen (top_y = 0) with concave top ears
      and smooth bottom corners.
    - Displays a balanced grayish perimeter backlight when hovered in either
      compact or expanded mode.
    - Supports free edge/corner resizing and fullscreen toggle on the open pill.
    """

    user_message_submitted: pyqtSignal = pyqtSignal(str)
    user_message_with_files_submitted: pyqtSignal = pyqtSignal(str, list)
    user_message_submitted_ex: pyqtSignal = pyqtSignal(str, list, bool)

    EAR_RADIUS = int(DIMENSIONS.get("ear_radius", 14))
    COMPACT_BOT_RADIUS = int(DIMENSIONS.get("compact_bottom_radius", 18))
    EXPANDED_BOT_RADIUS = int(DIMENSIONS.get("expanded_bottom_radius", 28))
    MIN_W_EXPANDED = int(DIMENSIONS.get("min_expanded_width", 360))
    MIN_H_EXPANDED = int(DIMENSIONS.get("min_expanded_height", 320))
    RESIZE_MARGIN = 10

    def __init__(self, on_user_submit_callback: Optional[Callable[[str], None]] = None):
        super().__init__()
        self._submit_cb = on_user_submit_callback
        self._is_expanded = False
        self._is_fullscreen = False
        self._is_hovered = False
        self._suppress_auto_collapse = False
        self._current_state = "idle"
        self._pending_request = False

        self._drag_pos: Optional[QPoint] = None
        self._press_pos: Optional[QPoint] = None
        self._drag_moved = False

        self._resize_edges: str = ""
        self._resize_start_pos: Optional[QPoint] = None
        self._resize_start_geom: Optional[QRect] = None
        self._pre_fullscreen_rect: Optional[QRect] = None

        self.W_COMPACT, self.H_COMPACT = self._resolve_compact_size()
        self.W_EXPANDED = int(DIMENSIONS.get("expanded_width", 480))
        self.H_EXPANDED = int(DIMENSIONS.get("expanded_height", 520))

        self._init_window()
        self._build_views()
        self._setup_animation()

        if LOGO_PATH.exists():
            self.setWindowIcon(QIcon(str(LOGO_PATH)))

        self.set_state("idle")

    def _resolve_compact_size(self) -> tuple[int, int]:
        """Compute logical pixel dimensions matching configured physical inches."""
        screen = self.screen() or QApplication.primaryScreen()
        fallback_w = int(DIMENSIONS.get("compact_width", 427))
        fallback_h = int(DIMENSIONS.get("compact_height", 48))

        w_in = DIMENSIONS.get("compact_width_inches")
        h_in = DIMENSIONS.get("compact_height_inches")
        if screen is None or w_in is None or h_in is None:
            return fallback_w, fallback_h

        dpr = max(screen.devicePixelRatio(), 1.0)
        px_per_inch = screen.physicalDotsPerInch() / dpr
        if not (40.0 <= px_per_inch <= 300.0):
            px_per_inch = 96.0

        w_px = max(210, min(700, int(round(float(w_in) * px_per_inch))))
        h_px = max(38, min(120, int(round(float(h_in) * px_per_inch))))
        return w_px, h_px

    def _init_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, True)
        self.setMouseTracking(True)

        screen = (self.screen() or QApplication.primaryScreen()).geometry()
        align = POSITION.get("align_x", "center")
        offset = int(POSITION.get("offset_x", 0))
        if align == "left":
            self._cx = screen.left() + self.W_COMPACT // 2 + 20 + offset
        elif align == "right":
            self._cx = screen.right() - self.W_COMPACT // 2 - 20 + offset
        else:
            self._cx = screen.center().x() + offset

        self._top_y = int(POSITION.get("top_y", 0))

        self.setGeometry(
            self._cx - self.W_COMPACT // 2,
            self._top_y,
            self.W_COMPACT,
            self.H_COMPACT,
        )

    def _build_views(self):
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(self.EAR_RADIUS, 0, self.EAR_RADIUS, 0)
        self._layout.setSpacing(0)

        self._compact_view = CompactCapsuleView(self)
        self._compact_view.hover_changed.connect(self._on_hover_changed)
        self._layout.addWidget(self._compact_view)

        self._conversation_card = ConversationCardView(self)
        self._conversation_card.close_requested.connect(self._quit_app)
        self._conversation_card.minimize_requested.connect(self._collapse)
        self._conversation_card.fullscreen_requested.connect(self.toggle_fullscreen)
        self._conversation_card.message_sent.connect(self._submit)
        self._conversation_card.file_dialog_state_changed.connect(self._on_file_dialog_state)
        self._conversation_card.hide()
        self._layout.addWidget(self._conversation_card)

        self._expanded_view = self._conversation_card

    def _on_file_dialog_state(self, is_open: bool):
        self._suppress_auto_collapse = is_open
        if not is_open and self._is_expanded:
            self.activateWindow()
            self._expanded_view._input_field.setFocus()

    def _on_hover_changed(self, hovered: bool):
        self._is_hovered = hovered or self.underMouse()
        self.update()

    def enterEvent(self, event: QEnterEvent):
        self._is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        if not self._resize_edges:
            self.unsetCursor()
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        if w <= 2 or h <= 2:
            return

        screen_avail = (self.screen() or QApplication.primaryScreen()).availableGeometry()
        if self._is_fullscreen and w >= screen_avail.width() - 4:
            p.fillRect(self.rect(), parse_color(NOTCH_BG, "#000000"))
            return

        denom = max(1.0, float(self.H_EXPANDED - self.H_COMPACT))
        t = max(0.0, min(1.0, (h - self.H_COMPACT) / denom))
        bot_r = self.COMPACT_BOT_RADIUS + t * (self.EXPANDED_BOT_RADIUS - self.COMPACT_BOT_RADIUS)

        fill_path, stroke_path = build_notch_paths(w, h, float(self.EAR_RADIUS), bot_r)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(parse_color(NOTCH_BG, "#000000")))
        p.drawPath(fill_path)

        # Balanced grayish perimeter backlight on BOTH compact and expanded windows
        p.save()
        p.setClipPath(fill_path)
        if self._is_hovered:
            hover_base = parse_color(NOTCH_BORDER_HOVER, "rgba(185, 188, 198, 0.56)")
            r, g, b = hover_base.red(), hover_base.green(), hover_base.blue()
            for width_px, alpha in ((9.0, 26), (5.0, 52), (2.5, 92)):
                glow_col = QColor(r, g, b, alpha)
                p.setPen(QPen(glow_col, width_px, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(stroke_path)
            p.setPen(QPen(hover_base, 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            p.drawPath(stroke_path)
        else:
            border_color = parse_color(NOTCH_BORDER, "rgba(255, 255, 255, 0.14)")
            pen = QPen(border_color, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(stroke_path)
        p.restore()

        if not self._is_expanded:
            cx = w / 2.0
            p.setPen(QPen(QColor(30, 44, 34, 180), 1.0))
            p.setBrush(QBrush(QColor(14, 23, 18)))
            p.drawEllipse(QRectF(cx - 2.5, 3.0, 5.0, 5.0))

    def _quit_app(self):
        """Shut down the Kugane desktop assistant completely."""
        QApplication.instance().quit()

    def changeEvent(self, event: QEvent):
        """Auto-collapse when the user clicks away or focus leaves the widget."""
        if event.type() == QEvent.Type.ActivationChange:
            if (
                not self.isActiveWindow()
                and self._is_expanded
                and not self._is_fullscreen
                and not self._suppress_auto_collapse
                and not (self._anim.state() == QPropertyAnimation.State.Running)
            ):
                self._collapse()
        super().changeEvent(event)

    def _setup_animation(self):
        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(240)
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
        screen = (self.screen() or QApplication.primaryScreen()).availableGeometry()
        w = max(self.MIN_W_EXPANDED, min(self.W_EXPANDED, screen.width()))
        h = max(self.MIN_H_EXPANDED, min(self.H_EXPANDED, screen.height()))
        x = max(screen.left(), min(self._cx - w // 2, screen.right() - w + 1))
        return QRect(x, self._top_y, w, h)

    def _fullscreen_rect(self) -> QRect:
        avail = (self.screen() or QApplication.primaryScreen()).availableGeometry()
        return QRect(avail.left(), self._top_y, avail.width(), avail.bottom() - self._top_y + 1)

    # ── State Machine ─────────────────────────────────────────────────────────

    def set_state(self, state: str, detail: str = ""):
        self._current_state = state

        if state == "idle":
            self._compact_view.set_idle_state()
            self._expanded_view.set_thinking(False)
        elif state == "thinking":
            self._compact_view.set_thinking_state(detail or "Thinking...")
            self._expanded_view.set_thinking(True)
        elif state == "loading":
            self._compact_view.set_loading_state(detail or "Loading...")
            self._expanded_view.set_thinking(False)
        elif state in ("error", "no_key"):
            self._compact_view.set_error_state(detail or "Error")
            self._expanded_view.set_thinking(False)

    def update_status(self, message: str):
        low = message.lower()
        if "loading" in low or "model" in low:
            self.set_state("loading", detail=message)
        elif "error" in low or "failed" in low:
            self.set_state("error", detail="Error")
        else:
            self.set_state("idle")

    # ── Expand / Collapse / Fullscreen ────────────────────────────────────────

    def _expand(self):
        if self._is_expanded or self._anim.state() == QPropertyAnimation.State.Running:
            return
        self._is_expanded = True

        self._compact_view.hide()
        self._expanded_view.show()

        target = self._fullscreen_rect() if self._is_fullscreen else self._expanded_rect()
        self._anim.stop()
        self._anim.setStartValue(self.geometry())
        self._anim.setEndValue(target)
        self._anim.start()

        self.activateWindow()
        self._expanded_view._input_field.setFocus()

    def _collapse(self):
        if not self._is_expanded or self._anim.state() == QPropertyAnimation.State.Running:
            return
        self._is_expanded = False
        if self._is_fullscreen:
            self._is_fullscreen = False
            self._layout.setContentsMargins(self.EAR_RADIUS, 0, self.EAR_RADIUS, 0)
            self._expanded_view.set_fullscreen_active(False)

        self._expanded_view.hide()
        self._compact_view.show()

        self._anim.stop()
        self._anim.setStartValue(self.geometry())
        self._anim.setEndValue(self._compact_rect())
        self._anim.start()

    def toggle_fullscreen(self):
        """Toggle between normal/custom expanded size and fullscreen."""
        if not self._is_expanded or self._anim.state() == QPropertyAnimation.State.Running:
            return

        if not self._is_fullscreen:
            self._pre_fullscreen_rect = QRect(self.geometry())
            self._is_fullscreen = True
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._expanded_view.set_fullscreen_active(True)
            target = self._fullscreen_rect()
        else:
            self._is_fullscreen = False
            self._layout.setContentsMargins(self.EAR_RADIUS, 0, self.EAR_RADIUS, 0)
            self._expanded_view.set_fullscreen_active(False)
            target = self._pre_fullscreen_rect or self._expanded_rect()

        self._anim.stop()
        self._anim.setStartValue(self.geometry())
        self._anim.setEndValue(target)
        self._anim.start()
        self.update()

    def _on_anim_finished(self):
        if not self._is_expanded:
            self.setGeometry(self._compact_rect())
        elif self._is_fullscreen:
            self.setGeometry(self._fullscreen_rect())
        self.update()

    # ── Conversation Pipeline ─────────────────────────────────────────────────

    def _submit(self, text: str, file_paths: list[str] | None = None, include_screen: bool = False):
        files = [f for f in (file_paths or []) if f]
        if (not text.strip() and not files and not include_screen) or self._pending_request:
            return
        self._pending_request = True

        if not self._is_expanded:
            self._expand()
        self._expanded_view.clear_agent_steps()
        display_text = text or ("[Live Screen Context]" if include_screen else "")
        self._expanded_view.add_user_message(display_text, file_paths=files)
        self.set_state("thinking")

        if self._submit_cb:
            self._submit_cb(text)
        if not files and not include_screen:
            self.user_message_submitted.emit(text)
        self.user_message_with_files_submitted.emit(text, files)
        self.user_message_submitted_ex.emit(text, files, include_screen)

    def on_agent_step(self, agent: str, title: str, detail: str, status: str):
        """Update the live Agent Activity feed inside the expanded card."""
        self._expanded_view.add_agent_step(agent, title, detail, status)

    def on_agent_status(self, status_text: str):
        """Update the compact notch status while multi-agent work runs."""
        if self._current_state == "thinking":
            self._compact_view.set_thinking_state(status_text)

    def on_llm_response(self, reply: str):
        self._pending_request = False
        self._expanded_view.add_assistant_message(reply)
        self.set_state("idle")

    def on_llm_error(self, error_msg: str):
        self._pending_request = False
        self._expanded_view.add_error_message(error_msg)
        self.set_state("error", detail="Error")

    def display_transcription(self, text: str):
        if not self._pending_request and text.strip():
            self._submit(text)

    def add_user_message(self, text: str, file_paths: list[str] | None = None):
        self._expanded_view.add_user_message(text, file_paths=file_paths)

    def add_assistant_message(self, text: str):
        self._expanded_view.add_assistant_message(text)
        self.set_state("idle")

    def add_error_message(self, text: str):
        self._expanded_view.add_error_message(text)
        self.set_state("error", detail="Error")

    # ── Resize Hit-Testing & Draggable Behavior ───────────────────────────────

    def _detect_resize_edges(self, local_pos: QPoint) -> str:
        if not self._is_expanded or self._is_fullscreen:
            return ""
        m = self.RESIZE_MARGIN
        left = local_pos.x() <= m
        right = local_pos.x() >= self.width() - m
        bottom = local_pos.y() >= self.height() - m
        if bottom and left:
            return "bottom_left"
        if bottom and right:
            return "bottom_right"
        if left:
            return "left"
        if right:
            return "right"
        if bottom:
            return "bottom"
        return ""

    def _update_cursor_for_edges(self, edges: str) -> None:
        if edges in ("left", "right"):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif edges == "bottom":
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        elif edges == "bottom_left":
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif edges == "bottom_right":
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        else:
            self.unsetCursor()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            local_pos = event.position().toPoint()
            edges = self._detect_resize_edges(local_pos)
            if edges:
                self._resize_edges = edges
                self._resize_start_pos = event.globalPosition().toPoint()
                self._resize_start_geom = QRect(self.geometry())
                event.accept()
                return

            self._press_pos = event.globalPosition().toPoint()
            self._drag_pos = self._press_pos - self.frameGeometry().topLeft()
            self._drag_moved = False
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._resize_edges and (event.buttons() & Qt.MouseButton.LeftButton):
            if self._resize_start_pos is None or self._resize_start_geom is None:
                return
            delta = event.globalPosition().toPoint() - self._resize_start_pos
            g = QRect(self._resize_start_geom)
            avail = (self.screen() or QApplication.primaryScreen()).availableGeometry()

            if "right" in self._resize_edges:
                new_w = max(self.MIN_W_EXPANDED, min(avail.right() - g.left() + 1, g.width() + delta.x()))
                g.setWidth(new_w)
            if "left" in self._resize_edges:
                max_left = g.right() - self.MIN_W_EXPANDED + 1
                new_left = max(avail.left(), min(max_left, g.left() + delta.x()))
                g.setLeft(new_left)
            if "bottom" in self._resize_edges:
                max_h = avail.bottom() - self._top_y + 1
                new_h = max(self.MIN_H_EXPANDED, min(max_h, g.height() + delta.y()))
                g.setHeight(new_h)

            self.setGeometry(g)
            self.W_EXPANDED = g.width()
            self.H_EXPANDED = g.height()
            self._cx = g.center().x()
            event.accept()
            return

        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            if self._is_fullscreen:
                return
            gpos = event.globalPosition().toPoint()
            if self._press_pos is not None and (gpos - self._press_pos).manhattanLength() > 4:
                self._drag_moved = True
            if self._drag_moved:
                new_pos = gpos - self._drag_pos
                screen = (self.screen() or QApplication.primaryScreen()).geometry()
                clamped_x = max(
                    screen.left(), min(new_pos.x(), screen.right() - self.width() + 1)
                )
                self.move(clamped_x, self._top_y)
                self._cx = self.geometry().center().x()
            event.accept()
            return

        edges = self._detect_resize_edges(event.position().toPoint())
        self._update_cursor_for_edges(edges)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._resize_edges:
                self._resize_edges = ""
                self._resize_start_pos = None
                self._resize_start_geom = None
                self._update_cursor_for_edges(self._detect_resize_edges(event.position().toPoint()))
                event.accept()
                return

            was_dragged = self._drag_moved
            self._drag_pos = None
            self._press_pos = None
            self._drag_moved = False
            if not was_dragged and not self._is_expanded:
                self._expand()
            event.accept()

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            if self._is_fullscreen:
                self.toggle_fullscreen()
                return
            if self._is_expanded:
                self._collapse()
                return
        elif self._is_expanded:
            if key == Qt.Key.Key_Down:
                self._expanded_view.smooth_scroll_by(110)
                return
            if key == Qt.Key.Key_Up:
                self._expanded_view.smooth_scroll_by(-110)
                return
            if key == Qt.Key.Key_PageDown:
                self._expanded_view.smooth_scroll_by(320)
                return
            if key == Qt.Key.Key_PageUp:
                self._expanded_view.smooth_scroll_by(-320)
                return
        super().keyPressEvent(event)
