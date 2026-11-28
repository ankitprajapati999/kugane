# -*- coding: utf-8 -*-
"""
ui/widgets.py — Reusable custom-painted UI primitives for Kugane.

Components:
  - KuganeLogoWidget   : Rounded-square rendering of ui/Assets/Final Logo.png
  - PulseDotWidget     : Breathing live status dot
  - WaveformWidget     : Animated 5-bar thinking indicator
  - AttachFileButton   : Circular paperclip media-upload trigger button
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QRect, QRectF, QTimer
from PyQt6.QtGui import (
    QBrush, QColor, QEnterEvent, QFont, QPainter, QPainterPath, QPen, QPixmap,
)
from PyQt6.QtWidgets import QPushButton, QWidget

from ui.theme import (
    ACCENT_GREEN, ACCENT_PRIMARY, LOGO_PATH, TEXT_MUTED, TEXT_PRIMARY,
    TEXT_SECONDARY, make_font,
)


class KuganeLogoWidget(QWidget):
    """Renders Kugane's official asset logo cropped into a crisp rounded square."""

    _cached_square_pixmap: Optional[QPixmap] = None

    def __init__(self, size: int = 38, radius: int = 9, parent=None):
        super().__init__(parent)
        self._size = size
        self._radius = radius
        self.setFixedSize(size, size)
        self._pixmap = self._load_square_pixmap()

    @classmethod
    def _load_square_pixmap(cls) -> Optional[QPixmap]:
        if cls._cached_square_pixmap is not None:
            return cls._cached_square_pixmap
        if not LOGO_PATH.exists():
            return None
        pm = QPixmap(str(LOGO_PATH))
        if pm.isNull():
            return None
        side = min(pm.width(), pm.height())
        margin = max(2, int(side * 0.035))
        crop_side = max(1, side - 2 * margin)
        x = (pm.width() - crop_side) // 2
        y = (pm.height() - crop_side) // 2
        cls._cached_square_pixmap = pm.copy(x, y, crop_side, crop_side)
        return cls._cached_square_pixmap

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        rect = QRectF(0.5, 0.5, self._size - 1.0, self._size - 1.0)
        clip = QPainterPath()
        clip.addRoundedRect(rect, self._radius, self._radius)

        p.save()
        p.setClipPath(clip)
        if self._pixmap is not None:
            dpr = self.devicePixelRatioF()
            target_px = max(1, int(round(self._size * dpr)))
            scaled = self._pixmap.scaled(
                target_px,
                target_px,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            scaled.setDevicePixelRatio(dpr)
            p.drawPixmap(0, 0, self._size, self._size, scaled)
        else:
            p.fillRect(self.rect(), QColor(ACCENT_PRIMARY))
            p.setPen(QColor("#000000"))
            p.setFont(make_font(self._size * 0.48, QFont.Weight.DemiBold))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "K")
        p.restore()

        p.setPen(QPen(QColor(255, 255, 255, 32), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, self._radius, self._radius)


class PulseDotWidget(QWidget):
    """Draws a smooth breathing / pulsing circular status indicator."""

    def __init__(self, color: str = ACCENT_GREEN, size: int = 10, parent=None):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)
        self._color = QColor(color)
        self._alpha = 230
        self._dir = -1
        self._pulsing = True

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(45)

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
        if self._alpha <= 135:
            self._alpha = 135
            self._dir = 1
        elif self._alpha >= 255:
            self._alpha = 255
            self._dir = -1
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        glow_color = QColor(self._color)
        glow_color.setAlpha(int(self._alpha * 0.28))
        p.setBrush(QBrush(glow_color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(0, 0, self._size, self._size)

        core_color = QColor(self._color)
        core_color.setAlpha(self._alpha)
        p.setBrush(QBrush(core_color))
        inset = max(1.5, self._size * 0.22)
        p.drawEllipse(
            QRectF(inset, inset, self._size - 2 * inset, self._size - 2 * inset)
        )


class WaveformWidget(QWidget):
    """Draws the 5 vertical waveform bars with dynamic thinking animation."""

    def __init__(self, color: str = ACCENT_PRIMARY, parent=None):
        super().__init__(parent)
        self.setFixedSize(22, 20)
        self._color = QColor(color)
        self._bars = [5, 10, 16, 10, 5]
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
            self._bars = [5, 10, 16, 10, 5]
            self.update()

    def _animate_tick(self):
        self._phase = (self._phase + 1) % 6
        presets = [
            [5, 10, 16, 10, 5],
            [6, 13, 18, 12, 6],
            [7, 16, 13, 15, 7],
            [6, 14, 18, 10, 5],
            [5, 11, 15, 13, 6],
            [4, 8, 12, 8, 4],
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


class AttachFileButton(QPushButton):
    """Circular media-upload button painted with a clean paperclip icon."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(36, 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Attach media (Photo, Document/PDF, Video, Audio, Code)")
        self._hovered = False
        self._has_files = False
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")

    def set_has_files(self, has_files: bool):
        self._has_files = has_files
        self.update()

    def enterEvent(self, event: QEnterEvent):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._hovered:
            bg = QColor("#24242B")
        elif self._has_files:
            bg = QColor(255, 212, 0, 28)
        else:
            bg = QColor("#18181D")

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bg))
        p.drawEllipse(0, 0, self.width(), self.height())

        if not self.isEnabled():
            icon_color = QColor(TEXT_MUTED)
        elif self._has_files or self._hovered:
            icon_color = QColor(ACCENT_PRIMARY if self._has_files else TEXT_PRIMARY)
        else:
            icon_color = QColor(TEXT_SECONDARY)

        pen = QPen(
            icon_color,
            1.7,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        cx, cy = self.width() / 2.0, self.height() / 2.0
        p.translate(cx, cy)
        p.rotate(-45.0)
        clip = QPainterPath()
        clip.moveTo(-4.5, -2.5)
        clip.lineTo(3.5, -2.5)
        clip.arcTo(QRectF(1.0, -2.5, 5.0, 5.0), 90.0, -180.0)
        clip.lineTo(-5.0, 2.5)
        clip.arcTo(QRectF(-7.0, -1.5, 4.0, 4.0), -90.0, -180.0)
        clip.lineTo(2.0, -0.5)
        p.drawPath(clip)


class ScreenVisionButton(QPushButton):
    """Toggleable circular Astra-style screen-vision button in the composer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(36, 36)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Look at current screen (Astra live context)")
        self._hovered = False
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")

    def enterEvent(self, event: QEnterEvent):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        active = self.isChecked()
        if active:
            bg = QColor(255, 212, 0, 38)
        elif self._hovered:
            bg = QColor("#24242B")
        else:
            bg = QColor("#18181D")

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bg))
        p.drawEllipse(0, 0, self.width(), self.height())

        if not self.isEnabled():
            icon_color = QColor(TEXT_MUTED)
        elif active:
            icon_color = QColor(ACCENT_PRIMARY)
        elif self._hovered:
            icon_color = QColor(TEXT_PRIMARY)
        else:
            icon_color = QColor(TEXT_SECONDARY)

        pen = QPen(
            icon_color,
            1.6,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        cx, cy = self.width() / 2.0, self.height() / 2.0
        eye = QPainterPath()
        eye.moveTo(cx - 8.5, cy)
        eye.quadTo(cx, cy - 6.5, cx + 8.5, cy)
        eye.quadTo(cx, cy + 6.5, cx - 8.5, cy)
        p.drawPath(eye)

        p.setBrush(QBrush(icon_color if active else Qt.BrushStyle.NoBrush))
        p.drawEllipse(QRectF(cx - 2.6, cy - 2.6, 5.2, 5.2))
