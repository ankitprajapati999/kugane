# -*- coding: utf-8 -*-
"""
ui/conversation_card.py — Expanded chat panel, media upload picker & composer.

Owns:
  - Header bar (Kugane logo, title, fullscreen/minimize/close controls)
  - Scrollable conversation feed + smooth scroll-to-bottom animation
  - Thinking status indicator
  - Categorized media upload menu (Photo, Document/PDF, Video, Audio, Code, Any)
  - Staged attachment chip strip & bottom message composer
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import (
    QEasingCurve, QEvent, QPoint, QPointF, QPropertyAnimation, QRectF,
    QStandardPaths, Qt, QTimer, pyqtSignal,
)
from PyQt6.QtGui import (
    QColor, QEnterEvent, QFont, QIcon, QKeyEvent, QPainter, QPainterPath,
    QPen, QPixmap,
)
from PyQt6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from core.media.file_processor import (
    MEDIA_CATEGORIES, FileProcessor, MediaCategory,
)
from ui.messages import AssistantMessageItem, UserMessageItem
from ui.theme import (
    ACCENT_GREEN, ACCENT_PRIMARY, ACCENT_PRIMARY_HOVER, ACCENT_RED,
    AI_BUBBLE_BORDER, AI_BUBBLE_END, AI_BUBBLE_START, COMPOSER_BORDER,
    COMPOSER_BOTTOM, COMPOSER_TOP, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    USER_BUBBLE_START, make_font,
)
from ui.widgets import (
    AttachFileButton, KuganeLogoWidget, ScreenVisionButton, WaveformWidget,
)


class _FullscreenButton(QPushButton):
    """Crisp vector fullscreen / restore toggle button for the upper-right header."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(26, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Full screen")
        self._active = False
        self._hovered = False
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")

    def set_fullscreen_active(self, active: bool) -> None:
        self._active = active
        self.setToolTip("Restore size" if active else "Full screen")
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
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#1A1A1E"))
            p.drawEllipse(0, 0, self.width(), self.height())

        color = QColor(TEXT_PRIMARY if self._hovered else TEXT_SECONDARY)
        p.setPen(QPen(color, 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)

        if not self._active:
            # Expand to fullscreen square corners
            p.drawRoundedRect(QRectF(7.5, 7.5, 11.0, 11.0), 2.0, 2.0)
        else:
            # Restore overlapping squares
            p.drawRoundedRect(QRectF(9.5, 6.5, 9.5, 9.5), 1.5, 1.5)
            p.setBrush(QColor("#000000"))
            p.drawRoundedRect(QRectF(7.0, 9.5, 9.5, 9.5), 1.5, 1.5)


class ConversationCardView(QWidget):
    """Expanded conversation panel rendered inside the unified pitch-black notch."""

    close_requested = pyqtSignal()
    minimize_requested = pyqtSignal()
    fullscreen_requested = pyqtSignal()
    message_sent = pyqtSignal(str, list, bool)
    file_dialog_state_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ConversationCard")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._attached_files: list[str] = []
        self._recorded_steps: list[tuple[str, str, str]] = []

        main_vbox = QVBoxLayout(self)
        main_vbox.setContentsMargins(18, 12, 18, 18)
        main_vbox.setSpacing(10)

        # ── Top bar: subtle sensor dot, Kugane logo & title, fullscreen/min/close
        sensor_row = QHBoxLayout()
        sensor_row.setContentsMargins(0, 0, 0, 0)
        sensor_row.addStretch()
        sensor = QFrame()
        sensor.setFixedSize(6, 6)
        sensor.setStyleSheet(
            "background-color: #0E1712; border: 1px solid #1E2C22; border-radius: 3px;"
        )
        sensor_row.addWidget(sensor)
        sensor_row.addStretch()
        main_vbox.addLayout(sensor_row)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(10)

        self._logo_badge = KuganeLogoWidget(size=34, radius=8)

        title_lbl = QLabel("Kugane")
        title_lbl.setFont(make_font(11.0, QFont.Weight.Medium))
        title_lbl.setStyleSheet(
            f"color: {TEXT_PRIMARY}; background: transparent; border: none;"
        )

        btn_box = QHBoxLayout()
        btn_box.setSpacing(6)

        self._fullscreen_btn = _FullscreenButton()
        self._fullscreen_btn.clicked.connect(self.fullscreen_requested.emit)

        min_btn = QPushButton("—")
        min_btn.setFixedSize(26, 26)
        min_btn.setFont(make_font(10.0, QFont.Weight.Normal))
        min_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        min_btn.setToolTip("Minimize")
        min_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_SECONDARY};
                border: none;
                border-radius: 13px;
            }}
            QPushButton:hover {{
                background: #1A1A1E;
                color: {TEXT_PRIMARY};
            }}
        """)
        min_btn.clicked.connect(self.minimize_requested.emit)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(26, 26)
        close_btn.setFont(make_font(9.5, QFont.Weight.Normal))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setToolTip("Close Kugane")
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_SECONDARY};
                border: none;
                border-radius: 13px;
            }}
            QPushButton:hover {{
                background: #2A1215;
                color: {ACCENT_RED};
            }}
        """)
        close_btn.clicked.connect(self.close_requested.emit)

        btn_box.addWidget(self._fullscreen_btn)
        btn_box.addWidget(min_btn)
        btn_box.addWidget(close_btn)

        header_row.addWidget(self._logo_badge, alignment=Qt.AlignmentFlag.AlignVCenter)
        header_row.addWidget(title_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)
        header_row.addStretch()
        header_row.addLayout(btn_box)
        main_vbox.addLayout(header_row)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFixedHeight(1)
        divider.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 transparent, stop:0.2 rgba(255, 255, 255, 0.12), "
            "stop:0.8 rgba(255, 255, 255, 0.12), stop:1 transparent); border: none;"
        )
        main_vbox.addWidget(divider)

        # ── Conversation Area (Scrollable) ────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 4px;
                margin: 0px;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.22);
                min-height: 24px;
                border-radius: 2px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        self._msg_container = QWidget()
        self._msg_container.setStyleSheet("background: transparent;")
        self._msg_vbox = QVBoxLayout(self._msg_container)
        self._msg_vbox.setContentsMargins(0, 4, 0, 4)
        self._msg_vbox.setSpacing(14)
        self._msg_vbox.addStretch(1)

        self._scroll.setWidget(self._msg_container)
        main_vbox.addWidget(self._scroll, stretch=1)

        self._scroll_anim = QPropertyAnimation(
            self._scroll.verticalScrollBar(), b"value", self
        )
        self._scroll_anim.setDuration(280)
        self._scroll_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._scroll.verticalScrollBar().valueChanged.connect(self._on_scroll_changed)

        # ── Scroll Down Indicator Pill ────────────────────────────────────────
        scroll_btn_row = QHBoxLayout()
        scroll_btn_row.setContentsMargins(0, 0, 0, 0)

        self._scroll_down_btn = QPushButton("↓")
        self._scroll_down_btn.setFixedSize(28, 28)
        self._scroll_down_btn.setFont(make_font(11.0, QFont.Weight.Normal))
        self._scroll_down_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._scroll_down_btn.setToolTip("Scroll to latest")
        self._scroll_down_btn.setStyleSheet(f"""
            QPushButton {{
                background: #141418;
                color: {TEXT_SECONDARY};
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 14px;
                padding-bottom: 2px;
            }}
            QPushButton:hover {{
                background: #1E1E24;
                color: {TEXT_PRIMARY};
                border: 1px solid rgba(185, 188, 198, 0.56);
            }}
        """)
        self._scroll_down_btn.clicked.connect(self.smooth_scroll_to_bottom)
        self._scroll_down_btn.hide()

        scroll_btn_row.addStretch()
        scroll_btn_row.addWidget(self._scroll_down_btn)
        scroll_btn_row.addStretch()
        main_vbox.addLayout(scroll_btn_row)

        # ── Thinking Status Bubble ────────────────────────────────────────────
        self._thinking_item = QWidget()
        t_layout = QVBoxLayout(self._thinking_item)
        t_layout.setContentsMargins(0, 0, 0, 0)
        t_layout.setSpacing(4)

        t_header = QLabel("KUGANE")
        t_header.setFont(make_font(8.8, QFont.Weight.Medium))
        t_header.setStyleSheet(
            f"color: {ACCENT_PRIMARY}; letter-spacing: 0.6px; background: transparent; border: none;"
        )

        t_bubble = QFrame()
        t_bubble.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {AI_BUBBLE_START}, stop:1 {AI_BUBBLE_END});
                border-radius: 14px;
                border: 1px solid {AI_BUBBLE_BORDER};
            }}
        """)
        tb_layout = QHBoxLayout(t_bubble)
        tb_layout.setContentsMargins(16, 10, 16, 10)
        tb_layout.setSpacing(10)

        self._thinking_lbl = QLabel("Thinking")
        self._thinking_lbl.setFont(make_font(10.0, QFont.Weight.Normal))
        self._thinking_lbl.setStyleSheet(
            f"color: {TEXT_PRIMARY}; background: transparent; border: none;"
        )

        self._thinking_wave = WaveformWidget(ACCENT_PRIMARY)
        self._thinking_wave.set_active(True)

        tb_layout.addWidget(self._thinking_lbl)
        tb_layout.addWidget(self._thinking_wave)

        t_row = QHBoxLayout()
        t_row.addWidget(t_bubble)
        t_row.addStretch()

        t_layout.addWidget(t_header)
        t_layout.addLayout(t_row)

        # Live Multi-Agent Activity Feed (updates as Supervisor/Agents work)
        self._agent_activity_box = QFrame()
        self._agent_activity_box.setStyleSheet(
            "QFrame { background: #0C0C0F; border: 1px solid rgba(255, 255, 255, 0.10); "
            "border-radius: 12px; }"
        )
        self._agent_steps_layout = QVBoxLayout(self._agent_activity_box)
        self._agent_steps_layout.setContentsMargins(12, 8, 12, 8)
        self._agent_steps_layout.setSpacing(4)
        self._agent_activity_box.hide()
        t_layout.addWidget(self._agent_activity_box)

        self._thinking_item.hide()
        main_vbox.addWidget(self._thinking_item)

        # ── Attached Files Chip Strip (shown when files are staged) ──────────
        self._attachments_bar = QWidget()
        self._attachments_bar.setStyleSheet("background: transparent;")
        self._attachments_layout = QHBoxLayout(self._attachments_bar)
        self._attachments_layout.setContentsMargins(4, 0, 4, 0)
        self._attachments_layout.setSpacing(6)
        self._attachments_layout.addStretch()
        self._attachments_bar.hide()
        main_vbox.addWidget(self._attachments_bar)

        # ── Bottom Message Composer ───────────────────────────────────────────
        self._composer_frame = QFrame()
        self._composer_frame.setFixedHeight(50)
        self._composer_frame.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {COMPOSER_TOP}, stop:1 {COMPOSER_BOTTOM});
                border: 1px solid {COMPOSER_BORDER};
                border-radius: 25px;
            }}
        """)
        c_layout = QHBoxLayout(self._composer_frame)
        c_layout.setContentsMargins(7, 6, 7, 6)
        c_layout.setSpacing(8)

        self._attach_btn = AttachFileButton()
        self._attach_btn.clicked.connect(self._on_attach_clicked)

        self._screen_btn = ScreenVisionButton()
        self._screen_btn.toggled.connect(lambda _on: self._on_text_changed(self._input_field.text()))

        self._input_field = QLineEdit()
        self._input_field.setPlaceholderText("Ask Kugane anything...")
        self._input_field.setFont(make_font(10.0, QFont.Weight.Normal))
        self._input_field.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {TEXT_PRIMARY};
                selection-background-color: {USER_BUBBLE_START};
            }}
        """)
        self._input_field.returnPressed.connect(self._on_submit)
        self._input_field.textChanged.connect(self._on_text_changed)
        self._input_field.installEventFilter(self)

        self._send_btn = QPushButton("↑")
        self._send_btn.setFixedSize(36, 36)
        self._send_btn.setFont(make_font(12.0, QFont.Weight.Medium))
        self._send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_btn.clicked.connect(self._on_submit)
        self._update_send_button(active=False)

        c_layout.addWidget(self._attach_btn)
        c_layout.addWidget(self._screen_btn)
        c_layout.addWidget(self._input_field, stretch=1)
        c_layout.addWidget(self._send_btn)

        main_vbox.addWidget(self._composer_frame)

    def set_fullscreen_active(self, active: bool) -> None:
        self._fullscreen_btn.set_fullscreen_active(active)

    def _current_bubble_max_width(self) -> int:
        w = self.width() if self.width() > 0 else 452
        return max(300, min(760, int(w * 0.72)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        max_w = self._current_bubble_max_width()
        for i in range(self._msg_vbox.count() - 1):
            item = self._msg_vbox.itemAt(i)
            widget = item.widget() if item is not None else None
            if hasattr(widget, "set_max_bubble_width"):
                widget.set_max_bubble_width(max_w)

    def eventFilter(self, obj, event):
        if obj is self._input_field and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Down:
                self.smooth_scroll_by(110)
                return True
            if key == Qt.Key.Key_Up:
                self.smooth_scroll_by(-110)
                return True
            if key == Qt.Key.Key_PageDown:
                self.smooth_scroll_by(max(180, int(self._scroll.viewport().height() * 0.85)))
                return True
            if key == Qt.Key.Key_PageUp:
                self.smooth_scroll_by(-max(180, int(self._scroll.viewport().height() * 0.85)))
                return True
        return super().eventFilter(obj, event)

    def _make_photo_icon(self) -> QIcon:
        pm = QPixmap(32, 32)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(TEXT_PRIMARY), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(4.0, 6.0, 24.0, 20.0), 4.0, 4.0)
        # Sun circle
        p.drawEllipse(QRectF(9.0, 10.5, 4.0, 4.0))
        # Mountain peaks
        mountain = QPainterPath()
        mountain.moveTo(6.0, 23.0)
        mountain.lineTo(13.0, 16.0)
        mountain.lineTo(18.0, 20.5)
        mountain.lineTo(22.0, 17.0)
        mountain.lineTo(26.5, 23.0)
        p.drawPath(mountain)
        p.end()
        return QIcon(pm)

    def _make_file_icon(self) -> QIcon:
        pm = QPixmap(32, 32)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(TEXT_PRIMARY), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        doc = QPainterPath()
        doc.moveTo(7.5, 4.5)
        doc.lineTo(19.0, 4.5)
        doc.lineTo(24.5, 10.0)
        doc.lineTo(24.5, 27.5)
        doc.lineTo(7.5, 27.5)
        doc.closeSubpath()
        p.drawPath(doc)
        # Folded corner
        p.drawLine(QPointF(19.0, 4.5), QPointF(19.0, 10.0))
        p.drawLine(QPointF(19.0, 10.0), QPointF(24.5, 10.0))
        # Document lines
        p.drawLine(QPointF(11.5, 15.5), QPointF(20.5, 15.5))
        p.drawLine(QPointF(11.5, 20.5), QPointF(18.5, 20.5))
        p.end()
        return QIcon(pm)

    def _build_media_menu(self) -> QMenu:
        """Create the 2-option media-upload popup menu (Photo / Image and File)."""
        menu = QMenu(self)
        menu.setFont(make_font(9.5, QFont.Weight.Normal))
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: #0D0D10;
                color: {TEXT_PRIMARY};
                border: 1px solid rgba(185, 188, 198, 0.36);
                border-radius: 12px;
                padding: 6px;
            }}
            QMenu::item {{
                padding: 7px 14px 7px 10px;
                border-radius: 8px;
            }}
            QMenu::item:selected {{
                background-color: #1D1D24;
                color: {ACCENT_PRIMARY};
            }}
            QMenu::icon {{
                padding-left: 4px;
            }}
        """)
        icons = {
            "photo": self._make_photo_icon(),
            "file": self._make_file_icon(),
        }
        for cat in MEDIA_CATEGORIES:
            action = menu.addAction(icons.get(cat.key, QIcon()), cat.label)
            action.setData(cat)
        return menu

    def _on_attach_clicked(self):
        menu = self._build_media_menu()
        self.file_dialog_state_changed.emit(True)
        selected_cat: MediaCategory | None = None
        try:
            menu.adjustSize()
            anchor = self._attach_btn.mapToGlobal(
                QPoint(0, -menu.sizeHint().height() - 6)
            )
            chosen_action = menu.exec(anchor)
            if chosen_action is not None:
                selected_cat = chosen_action.data()
        finally:
            if selected_cat is None:
                self.file_dialog_state_changed.emit(False)

        if selected_cat is None:
            return

        self._open_file_picker(selected_cat)

    def _resolve_initial_dir(self, category: MediaCategory) -> str:
        if category.key == "photo":
            pics = QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.PicturesLocation
            )
            if pics:
                return pics
            return str(Path.home() / "Pictures")
        return ""

    def _open_file_picker(self, category: MediaCategory):
        all_filters = (
            "All Files (*);;"
            "Images (*.png *.jpg *.jpeg *.webp *.gif *.bmp *.heic);;"
            "Documents (*.pdf *.txt *.md *.docx *.xlsx *.pptx *.csv *.json);;"
            "Videos (*.mp4 *.mov *.mkv *.webm *.avi);;"
            "Audio (*.mp3 *.wav *.m4a *.ogg *.flac)"
        )
        initial_dir = self._resolve_initial_dir(category)
        self.file_dialog_state_changed.emit(True)
        try:
            paths, _ = QFileDialog.getOpenFileNames(
                None,
                f"Upload {category.label}",
                initial_dir,
                all_filters,
                category.dialog_filter,
            )
        finally:
            self.file_dialog_state_changed.emit(False)

        if paths:
            for p in paths:
                if p and p not in self._attached_files:
                    self._attached_files.append(p)
            self._refresh_attachment_chips()
            self._input_field.setFocus()

    def _remove_attachment(self, path: str):
        if path in self._attached_files:
            self._attached_files.remove(path)
            self._refresh_attachment_chips()

    def _refresh_attachment_chips(self):
        while self._attachments_layout.count() > 1:
            item = self._attachments_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        for fp in self._attached_files:
            meta = FileProcessor.describe(fp)
            short = meta.name if len(meta.name) <= 16 else f"{meta.name[:13]}..."
            chip = QFrame()
            chip.setMinimumHeight(26)
            chip.setStyleSheet("""
                QFrame {
                    background: #16161B;
                    border: 1px solid rgba(255, 212, 0, 0.30);
                    border-radius: 13px;
                }
            """)
            cl = QHBoxLayout(chip)
            cl.setContentsMargins(8, 4, 6, 4)
            cl.setSpacing(6)

            badge_lbl = QLabel(meta.badge)
            badge_lbl.setFont(make_font(7.2, QFont.Weight.Medium))
            badge_lbl.setStyleSheet(
                f"color: #000000; background: {ACCENT_PRIMARY}; border: none; "
                "border-radius: 5px; padding: 1px 4px;"
            )

            lbl = QLabel(short)
            lbl.setFont(make_font(8.5, QFont.Weight.Normal))
            lbl.setStyleSheet(
                f"color: {TEXT_PRIMARY}; background: transparent; border: none;"
            )
            lbl.setToolTip(f"{meta.name} ({meta.size_label})\n{meta.path}")

            rm = QPushButton("×")
            rm.setFixedSize(16, 16)
            rm.setFont(make_font(9.5, QFont.Weight.Normal))
            rm.setCursor(Qt.CursorShape.PointingHandCursor)
            rm.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {TEXT_SECONDARY};
                    border: none;
                    border-radius: 8px;
                }}
                QPushButton:hover {{
                    color: {ACCENT_RED};
                }}
            """)
            rm.clicked.connect(lambda _checked=False, path=fp: self._remove_attachment(path))

            cl.addWidget(badge_lbl)
            cl.addWidget(lbl)
            cl.addWidget(rm)
            self._attachments_layout.insertWidget(self._attachments_layout.count() - 1, chip)

        has_files = bool(self._attached_files)
        self._attachments_bar.setVisible(has_files)
        self._attach_btn.set_has_files(has_files)
        self._on_text_changed(self._input_field.text())

    def _on_text_changed(self, text: str):
        is_active = bool(text.strip()) or bool(self._attached_files) or self._screen_btn.isChecked()
        self._update_send_button(active=is_active)

    def _update_send_button(self, active: bool):
        if active:
            self._send_btn.setEnabled(True)
            self._send_btn.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT_PRIMARY_HOVER}, stop:1 {ACCENT_PRIMARY});
                    color: #000000;
                    border: none;
                    border-radius: 18px;
                    padding-bottom: 2px;
                }}
                QPushButton:hover {{
                    background: {ACCENT_PRIMARY_HOVER};
                }}
            """)
        else:
            self._send_btn.setEnabled(False)
            self._send_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #1A1A1F;
                    color: {TEXT_MUTED};
                    border: none;
                    border-radius: 18px;
                    padding-bottom: 2px;
                }}
            """)

    def _on_submit(self):
        text = self._input_field.text().strip()
        files = list(self._attached_files)
        include_screen = self._screen_btn.isChecked()
        if text or files or include_screen:
            self._input_field.clear()
            self._attached_files.clear()
            self._refresh_attachment_chips()
            self._update_send_button(active=False)
            self.message_sent.emit(text, files, include_screen)

    def add_user_message(self, text: str, file_paths: list[str] | None = None):
        item = UserMessageItem(
            text,
            file_paths=file_paths,
            max_content_w=self._current_bubble_max_width(),
        )
        self._msg_vbox.insertWidget(self._msg_vbox.count() - 1, item)
        self._scroll_to_bottom()

    def clear_agent_steps(self):
        self._recorded_steps.clear()
        while self._agent_steps_layout.count():
            item = self._agent_steps_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._agent_activity_box.hide()

    def add_agent_step(self, agent: str, title: str, detail: str = "", status: str = "running"):
        # Update existing matching step if transitioning running -> done/error
        updated = False
        for i, (ag, tt, _st) in enumerate(self._recorded_steps):
            if ag == agent and tt == title:
                self._recorded_steps[i] = (agent, title, status)
                lbl = self._agent_steps_layout.itemAt(i).widget()
                if isinstance(lbl, QLabel):
                    self._style_step_label(lbl, agent, title, detail, status)
                updated = True
                break

        if not updated:
            self._recorded_steps.append((agent, title, status))
            lbl = QLabel()
            lbl.setFont(make_font(8.3, QFont.Weight.Normal))
            lbl.setWordWrap(True)
            self._style_step_label(lbl, agent, title, detail, status)
            self._agent_steps_layout.addWidget(lbl)

        self._thinking_lbl.setText(f"{agent}: {title}" if status == "running" else "Thinking")
        self._agent_activity_box.show()
        self._scroll_to_bottom()

    @staticmethod
    def _style_step_label(lbl: QLabel, agent: str, title: str, detail: str, status: str) -> None:
        if status == "done":
            icon, color = "✓", ACCENT_GREEN
        elif status == "error":
            icon, color = "✕", ACCENT_RED
        else:
            icon, color = "●", ACCENT_PRIMARY
        suffix = f" ({detail})" if detail and detail != "Completed" else ""
        lbl.setText(f"{icon} {agent} — {title}{suffix}")
        lbl.setStyleSheet(f"color: {color}; background: transparent; border: none;")

    def add_assistant_message(self, text: str):
        # Preserve only specialist / tool steps (skip generic Supervisor wrapper noise if plain chat)
        meaningful_steps = [
            s for s in self._recorded_steps
            if s[0] != "Supervisor" or "Delegating" in s[1]
        ]
        item = AssistantMessageItem(
            text,
            max_content_w=self._current_bubble_max_width(),
            agent_steps=meaningful_steps,
        )
        self.clear_agent_steps()
        self._msg_vbox.insertWidget(self._msg_vbox.count() - 1, item)
        self._scroll_to_bottom()

    def add_error_message(self, text: str):
        self.clear_agent_steps()
        item = AssistantMessageItem(
            f"⚠ {text}",
            max_content_w=self._current_bubble_max_width(),
        )
        self._msg_vbox.insertWidget(self._msg_vbox.count() - 1, item)
        self._scroll_to_bottom()

    def set_thinking(self, thinking: bool):
        self._thinking_item.setVisible(thinking)
        self._input_field.setEnabled(not thinking)
        self._attach_btn.setEnabled(not thinking)
        self._screen_btn.setEnabled(not thinking)
        self._send_btn.setEnabled(
            not thinking
            and (
                bool(self._input_field.text().strip())
                or bool(self._attached_files)
                or self._screen_btn.isChecked()
            )
        )
        if thinking:
            self._thinking_lbl.setText("Thinking")
            self._thinking_wave.set_active(True)
            self._scroll_to_bottom()
        else:
            self._thinking_wave.set_active(False)

    def _on_scroll_changed(self, val: int):
        max_val = self._scroll.verticalScrollBar().maximum()
        self._scroll_down_btn.setVisible(max_val > 50 and (max_val - val) > 30)

    def _animate_scroll_to(self, target_val: int):
        sb = self._scroll.verticalScrollBar()
        clamped = max(0, min(sb.maximum(), target_val))
        self._scroll_anim.stop()
        self._scroll_anim.setStartValue(sb.value())
        self._scroll_anim.setEndValue(clamped)
        self._scroll_anim.start()

    def smooth_scroll_by(self, delta_px: int):
        sb = self._scroll.verticalScrollBar()
        base = (
            self._scroll_anim.endValue()
            if self._scroll_anim.state() == QPropertyAnimation.State.Running
            else sb.value()
        )
        self._animate_scroll_to(int(base) + delta_px)

    def smooth_scroll_to_bottom(self):
        self._animate_scroll_to(self._scroll.verticalScrollBar().maximum())

    def _scroll_to_bottom(self):
        QTimer.singleShot(50, self.smooth_scroll_to_bottom)
